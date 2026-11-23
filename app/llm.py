"""LLM 抽象层：OpenAI 兼容客户端 + 零配置的确定性 MockLLM。

- MockLLM：关键词分类 + 模板化回答，回答中的事实全部来自工具结果，
  并带 【来源:xxx】 标记；token 计数为固定值，便于成本精确复现。
- OpenAICompatibleLLM：通过环境变量配置的 OpenAI 兼容端点。
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

import httpx

from .intents import classify_intent
from .schemas import IntentEnum, ToolResult


@dataclass
class LLMAnswer:
    """LLM 生成的答案及其 token 用量。"""

    text: str
    token_in: int
    token_out: int


class LLMClient(ABC):
    """可被替换的 LLM 客户端接口。"""

    @abstractmethod
    def classify(self, text: str) -> Tuple[IntentEnum, float]:
        """意图分类。"""

    @abstractmethod
    def answer(
        self,
        intent: IntentEnum,
        tool_results: List[ToolResult],
        *,
        concise: bool = True,
        order_id: str | None = None,
    ) -> LLMAnswer:
        """基于工具结果生成带来源标记的答案。"""


class MockLLM(LLMClient):
    """确定性 Mock：无需 API Key，答案只使用工具结果中的字段。"""

    def classify(self, text: str) -> Tuple[IntentEnum, float]:
        return classify_intent(text)

    @staticmethod
    def _result(
        tool_results: List[ToolResult], tool_name: str
    ) -> ToolResult | None:
        for result in tool_results:
            if result.tool_name == tool_name and result.success:
                return result
        return None

    @staticmethod
    def _no_grounding() -> str:
        # 故意不带来源标记：会被 citations.verify_citations 拦下并转人工
        return "抱歉，当前缺少可核验的订单或政策信息，无法给出确定答复，已为您转人工客服。"

    def answer(
        self,
        intent: IntentEnum,
        tool_results: List[ToolResult],
        *,
        concise: bool = True,
        order_id: str | None = None,
    ) -> LLMAnswer:
        text = self._compose(intent, tool_results)
        # 确定性 token 计量：简洁提示词显著降低 token 用量
        token_in = 440 if concise else 640
        token_out = 90 if concise else 120
        return LLMAnswer(text=text, token_in=token_in, token_out=token_out)

    def _compose(
        self, intent: IntentEnum, tool_results: List[ToolResult]
    ) -> str:
        order = self._result(tool_results, "query_order")
        policy = self._result(tool_results, "check_refund_policy")
        logistics = self._result(tool_results, "query_logistics")

        if intent == IntentEnum.RETURN:
            if order is None or policy is None:
                return self._no_grounding()
            oid = order.data["order_id"]
            return (
                f"您好，订单 {oid}（{order.data['item']}）当前状态为「{order.data['status']}」。"
                f"依据退货政策，签收后 {policy.data['window_days']} 天内可申请退货，商品需保持完好；"
                f"仓库签收后约 3 个工作日完成处理。"
                f"【来源:{order.source_id}】【来源:{policy.source_id}】"
            )

        if intent == IntentEnum.LOGISTICS:
            if order is None or logistics is None:
                return self._no_grounding()
            return (
                f"您好，订单 {logistics.data['order_id']} 由 {logistics.data['carrier']} 承运，"
                f"运单号 {logistics.data['tracking_no']}，最新状态：{logistics.data['logistics_status']}，"
                f"预计 {logistics.data['eta']} 送达。"
                f"【来源:{logistics.source_id}】"
            )

        if intent == IntentEnum.REFUND:
            if order is None or policy is None:
                return self._no_grounding()
            oid = order.data["order_id"]
            return (
                f"已查询到订单 {oid} 的退款申请信息，金额约 ¥{order.data['amount']}，"
                f"退款窗口 {policy.data['window_days']} 天。退款涉及资金操作，"
                f"必须由人工审核后处理，已为您提交审批。"
                f"【来源:{order.source_id}】【来源:{policy.source_id}】"
            )

        return self._no_grounding()


def _extract_json(raw: str) -> dict:
    """容忍模型返回 ```json 代码块或纯 JSON。"""
    cleaned = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"模型未返回 JSON: {raw[:200]}")
    return json.loads(match.group(0))


class OpenAICompatibleLLM(LLMClient):
    """OpenAI 兼容端点客户端（/chat/completions）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-3.5-turbo",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _complete(self, system: str, user: str) -> Tuple[dict, int, int]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage", {})
        token_in = int(usage.get("prompt_tokens", len(system + user) // 4))
        token_out = int(usage.get("completion_tokens", len(content) // 4))
        return _extract_json(content), token_in, token_out

    def classify(self, text: str) -> Tuple[IntentEnum, float]:
        system = (
            "你是电商售后意图分类器。只输出 JSON："
            '{"intent":"return|logistics|refund|unknown","confidence":0.0~1.0}。'
            "涉及资金退款优先判为 refund。"
        )
        data, _, _ = self._complete(system, f"用户咨询：{text}")
        try:
            return IntentEnum(data["intent"]), float(data.get("confidence", 0.0))
        except (KeyError, ValueError):
            return IntentEnum.UNKNOWN, 0.0

    def answer(
        self,
        intent: IntentEnum,
        tool_results: List[ToolResult],
        *,
        concise: bool = True,
        order_id: str | None = None,
    ) -> LLMAnswer:
        system = (
            "你是电商售后客服。只能依据给定的工具结果回答，"
            "每个事实后必须加【来源:source_id】标记；没有可靠依据就回答"
            "「抱歉，当前缺少可核验的信息，已为您转人工客服。」且不要加任何来源标记。"
            "只输出 JSON：{\"answer\":\"...\"}。"
        )
        facts = "\n".join(
            f"- 来源 {r.source_id}（{r.tool_name}）: {json.dumps(r.data, ensure_ascii=False)}"
            for r in tool_results
        )
        data, token_in, token_out = self._complete(
            system, f"意图：{intent.value}\n工具结果：\n{facts or '（无）'}"
        )
        return LLMAnswer(
            text=str(data.get("answer", "")), token_in=token_in, token_out=token_out
        )


def build_llm_from_env() -> LLMClient:
    """根据环境变量选择 LLM 实现；默认 MockLLM，零配置可运行。"""
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openai 时必须设置 OPENAI_API_KEY")
        return OpenAICompatibleLLM(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        )
    return MockLLM()
