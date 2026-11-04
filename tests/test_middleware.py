# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Credential middleware (TC2, TC22): 401 on missing/empty header, per-request isolation."""

import asyncio

import pytest
from starlette.testclient import TestClient

from netlify_mcp import api_client
from netlify_mcp.__main__ import build_http_app
from netlify_mcp.middleware import CredentialsMiddleware, _credentials_var, get_client_from_context
from netlify_mcp.server import create_mcp_server

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
CREDS = {"X-Netlify-Token": "nfp_test_token"}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Netlify-Token": ""}, {"X-Netlify-Token": "   "}])
def test_missing_or_empty_token_returns_401(headers):
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | headers)
    assert resp.status_code == 401
    assert resp.json()["required_headers"] == ["X-Netlify-Token"]
    assert "X-Netlify-Token" in resp.json()["message"]


def test_missing_token_header_returns_401_and_no_upstream_call(monkeypatch):
    """TC2 (AC2): no X-Netlify-Token -> 401 naming it, and Netlify is never called."""
    calls: list = []

    async def fake_request(self, method, path, params=None, body=None):
        calls.append((method, path))
        raise AssertionError("must not reach Netlify without a valid token")

    monkeypatch.setattr(api_client.NetlifyClient, "request", fake_request)
    call_tool = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "netlify_list_sites", "arguments": {}}}
    with _client() as client:
        resp = client.post("/mcp", json=call_tool, headers=MCP_HEADERS)
    assert resp.status_code == 401
    assert calls == []


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    for name in ("netlify_list_sites", "netlify_delete_dns_record", "netlify_test_connection"):
        assert name in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(CredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


def test_credentials_reach_request_context_and_are_reset():
    seen = _run_middleware([(b"x-netlify-token", b" token-123 ")])
    client = seen["client"]
    assert client._headers()["Authorization"] == "Bearer token-123"
    assert _credentials_var.get() is None  # reset after the request


def test_credentials_repr_hides_token():
    seen = _run_middleware([(b"x-netlify-token", b"very-secret-token")])
    assert "very-secret-token" not in repr(seen["credentials"])


def test_concurrent_tokens_do_not_leak_between_contexts():
    """TC22 (AC13): two concurrent requests with different tokens never see each other's context."""
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().token
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().token))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = CredentialsMiddleware(app)

    def scope(token: bytes) -> dict:
        return {"type": "http", "path": "/mcp", "headers": [(b"x-netlify-token", token)]}

    async def both():
        await asyncio.gather(middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send))

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_client_outside_a_request_is_none():
    assert get_client_from_context() is None
