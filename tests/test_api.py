"""FastAPI 接口冒烟测试（使用 MockLLM，零 API Key）。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_root():
    assert client.get("/health").json() == {"status": "ok"}
    # 根路径现在返回图形界面首页；原 JSON 元信息保留在 /api/info
    assert client.get("/api/info").json()["provider"] == "mock"
    assert "<html" in client.get("/").text


def test_tools_endpoint():
    names = [item["name"] for item in client.get("/tools").json()]
    assert "query_order" in names
    assert "approve_refund" not in names


def test_chat_and_approval_flow():
    auto = client.post("/chat", json={"text": "订单 ORD1011 想退货"}).json()
    assert auto["tier"] == "auto_reply"
    assert auto["auto_resolved"] is True

    refund = client.post("/chat", json={"text": "订单 ORD1012 我要退款"}).json()
    assert refund["tier"] == "human_approval"
    ticket_id = refund["approval_id"]

    pending = client.get("/approvals", params={"status": "pending"}).json()
    assert any(t["id"] == ticket_id for t in pending)

    approved = client.post(f"/approvals/{ticket_id}/approve").json()
    assert approved["status"] == "approved"


def test_formula_endpoint():
    assert "net_resolved" in client.get("/metrics/formula").json()["formula"]
