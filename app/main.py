"""FastAPI 服务入口：同时提供 JSON API 与浏览器可操作的 Web GUI。

启动：
    uvicorn app.main:app --reload
默认使用 MockLLM，无需任何 API Key。

浏览器打开 http://127.0.0.1:8000 即可看到图形界面；
原有 JSON API（/chat、/approvals、/tools 等）行为保持不变，
原根路径的 JSON 信息迁移到 /api/info。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import VERSION_PRESETS, AfterSalesAgent
from .approval import ApprovalQueue
from .llm import build_llm_from_env
from .metrics import FORMULA_DOC
from .schemas import ApprovalStatus, ApprovalTicket, CustomerMessage
from .tools import ToolRegistry

app = FastAPI(
    title="售后星 · 电商售后 AI 助手",
    version="1.0.0",
    description="覆盖退货、查物流、退款三类咨询的分级 Agent（MockLLM 零配置可运行）",
)

# 进程级共享组件
llm = build_llm_from_env()
approval_queue = ApprovalQueue()
tool_registry = ToolRegistry()

# 静态前端目录：<项目根>/static
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ApproveRequest(BaseModel):
    """人工审批决策请求（预留扩展字段）。"""

    note: Optional[str] = None


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """根路径返回图形界面首页。"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/info")
def info() -> dict:
    """原根路径的 JSON 元信息（GUI 接管根路径后保留在此）。"""
    return {
        "name": "售后星 · 电商售后 AI 助手",
        "provider": os.getenv("LLM_PROVIDER", "mock"),
        "endpoints": ["/chat", "/approvals", "/tools", "/metrics/formula",
                      "/eval/historical", "/eval/ab"],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/tools")
def tools() -> List[dict]:
    """返回工具白名单（退款审批不在其中）。"""
    return tool_registry.list_tools()


@app.get("/metrics/formula")
def formula() -> dict:
    """返回净解决率的精确定义，便于核对口径。"""
    return {"formula": FORMULA_DOC}


@app.get("/eval/historical")
def eval_historical() -> dict:
    """返回 eval/fixtures.py 中固化的历史实测结果（简历数字来源）。"""
    from eval.fixtures import HISTORICAL_RESULTS

    return HISTORICAL_RESULTS


@app.post("/eval/ab")
def eval_ab() -> dict:
    """用 MockLLM 实时跑 200 条用例，比较 v1 / v2 的解决率与单笔成本。"""
    from eval.ab import build_report
    from eval.cases import load_cases

    return build_report(load_cases())


@app.post("/chat")
def chat(message: CustomerMessage, version: str = Query("v2", pattern="^(v1|v2)$")):
    """处理一条售后咨询。version 可在 v1 / v2 间切换以观察差异。"""
    agent = AfterSalesAgent(
        llm=llm,
        tools=tool_registry,
        approvals=approval_queue,
        config=VERSION_PRESETS[version],
    )
    return agent.handle(message)


@app.get("/approvals", response_model=List[ApprovalTicket])
def list_approvals(status: Optional[ApprovalStatus] = None) -> List[ApprovalTicket]:
    """查看审批队列，可按 pending / approved / rejected 过滤。"""
    return approval_queue.list(status)


def _decide(ticket_id: str, status: ApprovalStatus) -> ApprovalTicket:
    ticket = approval_queue.decide(ticket_id, status)
    if ticket is None:
        raise HTTPException(status_code=404, detail="审批工单不存在")
    return ticket


@app.post("/approvals/{ticket_id}/approve", response_model=ApprovalTicket)
def approve(ticket_id: str, request: ApproveRequest = ApproveRequest()) -> ApprovalTicket:
    return _decide(ticket_id, ApprovalStatus.APPROVED)


@app.post("/approvals/{ticket_id}/reject", response_model=ApprovalTicket)
def reject(ticket_id: str, request: ApproveRequest = ApproveRequest()) -> ApprovalTicket:
    return _decide(ticket_id, ApprovalStatus.REJECTED)


# 静态资源挂载放在路由之后，避免影响 API 路由匹配
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
