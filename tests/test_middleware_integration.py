"""Integration tests for APISentinelMiddleware runtime capture."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api_sentinel.middleware import APISentinelMiddleware
from api_sentinel.runtime_data import RuntimeData


@pytest.fixture
def capture_app(tmp_path):
    """Minimal app with middleware; stores captured RuntimeData."""
    captured: list[RuntimeData] = []

    async def fake_process(self, data: RuntimeData) -> None:
        captured.append(data)

    app = FastAPI()
    app.add_middleware(
        APISentinelMiddleware,
        openapi_path=str(tmp_path / "openapi.yaml"),
        enabled=True,
    )

    # Minimal openapi spec so parser doesn't fail
    (tmp_path / "openapi.yaml").write_text(
        "openapi: '3.0.0'\ninfo:\n  title: test\n  version: '1.0'\npaths: {}\n"
    )

    @app.get("/api/v1/users/{user_id}")
    async def get_user(user_id: int):
        return JSONResponse({"id": user_id, "name": "Alice"})

    @app.post("/api/v1/auth/login")
    async def login():
        return JSONResponse({"access_token": "tok"}, status_code=200)

    with patch.object(APISentinelMiddleware, "_process_captured_data", fake_process):
        yield app, captured


def test_middleware_captures_path_parameters(capture_app):
    app, captured = capture_app
    client = TestClient(app)
    resp = client.get("/api/v1/users/42", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200
    assert resp.json() == {"id": 42, "name": "Alice"}
    assert len(captured) == 1
    data = captured[0]
    assert data.method == "GET"
    assert data.endpoint == "/api/v1/users/42"
    assert data.path_parameters == {"user_id": "42"}
    assert data.authentication_type == "Bearer Token"
    assert data.status_code == 200
    assert data.response_body == {"id": 42, "name": "Alice"}
    assert data.request_headers["authorization"] == "Bearer [REDACTED]"


def test_middleware_captures_post_body(capture_app):
    app, captured = capture_app
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret"},
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert len(captured) == 1
    data = captured[0]
    assert data.method == "POST"
    assert data.request_body == {"username": "alice", "password": "secret"}


def test_middleware_api_key_query_param_case_insensitive(capture_app):
    app, captured = capture_app
    client = TestClient(app)
    resp = client.get("/api/v1/users/1?API_KEY=secret")
    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].authentication_type == "API Key"
