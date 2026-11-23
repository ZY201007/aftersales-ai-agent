"""答案引用（Answer-with-Citations）与反幻觉校验。

规则：
1. 每个事实性回答必须用 【来源:xxx】 标记指向真实存在的工具结果；
2. 校验器会核对标记、引用列表与工具结果集合三者一致；
3. 任一校验失败 => 拒绝直接作答，转人工兜底（宁可少答，不可编造）。
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .schemas import Citation, ToolResult

# 形如 【来源:order:ORD1001】
CITATION_PATTERN = re.compile(r"【来源:([^】]+)】")


def extract_source_ids(text: str) -> List[str]:
    """抽取答案文本中出现的全部来源 ID。"""
    return CITATION_PATTERN.findall(text or "")


def _snippet(result: ToolResult, max_items: int = 4) -> str:
    """把工具结果压成一行摘要，便于人工复核。"""
    pairs = list(result.data.items())[:max_items]
    return "；".join(f"{k}={v}" for k, v in pairs)


def build_citations(answer_text: str, tool_results: List[ToolResult]) -> List[Citation]:
    """根据答案中的来源标记，从真实工具结果生成引用对象。"""
    by_source = {r.source_id: r for r in tool_results if r.success}
    citations: List[Citation] = []
    for source_id in extract_source_ids(answer_text):
        result = by_source.get(source_id)
        snippet = _snippet(result) if result else "（来源未找到对应工具结果）"
        citations.append(Citation(source_id=source_id, snippet=snippet))
    return citations


def verify_citations(
    answer_text: str,
    citations: List[Citation],
    tool_results: List[ToolResult],
) -> Tuple[bool, str]:
    """反幻觉校验。返回 (是否通过, 原因)。"""
    if not (answer_text or "").strip():
        return False, "答案为空"

    known_sources = {r.source_id for r in tool_results if r.success}
    if not known_sources:
        return False, "没有任何可核验的工具结果，禁止作答"

    if not citations:
        return False, "答案未携带任何来源引用"

    cited_ids = {c.source_id for c in citations}
    unknown = cited_ids - known_sources
    if unknown:
        return False, f"引用了不存在的来源: {sorted(unknown)}"

    # 答案内标记必须与引用列表完全一致，防止「有引用但答案乱标」
    marked_ids = set(extract_source_ids(answer_text))
    if marked_ids != cited_ids:
        return False, "答案中的来源标记与引用列表不一致"

    if not marked_ids:
        return False, "答案缺少来源标记"

    return True, "ok"
