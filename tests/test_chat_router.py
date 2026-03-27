# tests/test_chat_router.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.fixture
def client():
    with patch.dict("os.environ", {"DASHBOARD_API_KEY": "", "VERCEL_ORIGIN": "http://localhost:3000"}):
        from backend.config import get_settings
        get_settings.cache_clear()
        from backend.main import app
        yield TestClient(app)

def test_chat_returns_answer(client):
    with patch("backend.routers.chat.ask_agent") as mock_agent:
        mock_agent.return_value = "BTC 현재 분석 중입니다."
        resp = client.post("/chat", json={"message": "BTC 어때?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["answer"] == "BTC 현재 분석 중입니다."

def test_chat_empty_message_returns_422(client):
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422
