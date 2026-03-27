# tests/test_api_key_auth.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

def test_missing_api_key_returns_401():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 401

def test_wrong_api_key_returns_401():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

def test_correct_api_key_returns_200():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200

def test_health_check_skips_auth():
    """/ 경로는 인증 없이 통과해야 함"""
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/")
    def root():
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/")
    assert resp.status_code == 200
