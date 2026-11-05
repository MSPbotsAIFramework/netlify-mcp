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
"""tools/list snapshot, error-envelope mapping, and per-tool behaviour against a
mocked Netlify API (httpx.MockTransport). No network access; no real Netlify account.
"""

import asyncio
import json

import httpx
import pytest

from netlify_mcp import api_client
from netlify_mcp.api_client import NetlifyCredentials, NetlifyError
from netlify_mcp.middleware import _credentials_var
from netlify_mcp.server import INSTRUCTIONS, create_mcp_server

ID = {"id"}
CREDS = NetlifyCredentials("token-123")

# Tool names are a public contract: existing agents and tenant connections depend
# on them. Changing this snapshot is a breaking change (SOP §13).
EXPECTED_TOOLS: dict[str, set[str]] = {
    "netlify_test_connection": set(),
    "netlify_list_accounts": set(),
    "netlify_list_sites": set(),
    "netlify_get_site": {"site_id"},
    "netlify_create_site": set(),
    "netlify_update_site": {"site_id"},
    "netlify_delete_site": {"site_id"},
    "netlify_list_deploys": {"site_id"},
    "netlify_get_deploy": {"site_id", "deploy_id"},
    "netlify_restore_deploy": {"site_id", "deploy_id"},
    "netlify_list_site_env_vars": {"site_id"},
    "netlify_list_account_env_vars": {"account_id"},
    "netlify_get_env_var": {"account_id", "key"},
    "netlify_create_env_var": {"account_id", "key", "values"},
    "netlify_set_env_var_value": {"account_id", "key", "value"},
    "netlify_delete_env_var": {"account_id", "key"},
    "netlify_list_forms": {"site_id"},
    "netlify_delete_form": {"site_id", "form_id"},
    "netlify_list_site_submissions": {"site_id"},
    "netlify_list_form_submissions": {"form_id"},
    "netlify_mark_submission_spam": {"submission_id"},
    "netlify_mark_submission_ham": {"submission_id"},
    "netlify_delete_submission": {"submission_id"},
    "netlify_list_dns_zones": set(),
    "netlify_get_dns_zone": {"zone_id"},
    "netlify_create_dns_zone": {"name"},
    "netlify_delete_dns_zone": {"zone_id"},
    "netlify_list_dns_records": {"zone_id"},
    "netlify_get_dns_record": {"zone_id", "record_id"},
    "netlify_create_dns_record": {"zone_id", "type", "hostname", "value"},
    "netlify_delete_dns_record": {"zone_id", "record_id"},
}
DESTRUCTIVE_TOOLS = {n for n in EXPECTED_TOOLS if "_delete_" in n} | {"netlify_restore_deploy"}
READ_TOOLS = {n for n in EXPECTED_TOOLS if n.startswith(("netlify_list_", "netlify_get_")) or n == "netlify_test_connection"}
CONFIRM_TOOLS = DESTRUCTIVE_TOOLS  # every destructive tool here needs confirm: true


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_are_stable(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


def test_tools_list_snapshot(tools):
    """TC25: exactly 31 tools; no description over 500 chars / first line over 100."""
    assert len(tools) == 31
    for name, tool in tools.items():
        description = (tool.description or "").strip()
        assert description, f"{name} has no description"
        assert len(description) <= 500, f"{name} description too long ({len(description)} chars)"
        assert len(description.splitlines()[0]) <= 100, f"{name} first line too long"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations_match_side_effects(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name in READ_TOOLS)
    assert bool(annotations.destructiveHint) is (name in DESTRUCTIVE_TOOLS)


@pytest.mark.parametrize("name", sorted(set(EXPECTED_TOOLS) - READ_TOOLS))
def test_write_tools_say_when_to_use_them(tools, name):
    assert "explicitly ask" in tools[name].description


@pytest.mark.parametrize("name", sorted(CONFIRM_TOOLS))
def test_destructive_tools_take_confirm(tools, name):
    assert "confirm" in tools[name].inputSchema["properties"]


def test_per_page_is_capped_at_100(tools):
    paged = [t for t in tools.values() if "per_page" in t.inputSchema["properties"]]
    for tool in paged:
        assert tool.inputSchema["properties"]["per_page"]["anyOf"][0]["maximum"] == 100, tool.name
    content, _ = asyncio.run(create_mcp_server().call_tool("netlify_list_sites", {"per_page": 101}))
    error = json.loads(content[0].text)["error"]
    assert error["code"] == "invalid_argument" and "less than or equal to 100" in error["message"]


def test_instructions_budget():
    assert len(INSTRUCTIONS) <= 1500


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (409, "invalid_argument", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (0, "upstream_error", True),
    ],
)
def test_error_envelope(status, code, retryable):
    envelope = json.loads(NetlifyError(status, "boom").to_envelope())
    assert envelope == {"error": {"code": code, "message": "boom", "retryable": retryable}}


def test_tool_without_credentials_returns_not_configured():
    content, _ = asyncio.run(create_mcp_server().call_tool("netlify_list_sites", {}))
    assert json.loads(content[0].text)["error"]["code"] == "not_configured"


# ---- stubbed-API functional tests (Recorder = a mock httpx transport) ----------


class Recorder:
    """Mock transport: replies by method + path below /api/v1/."""

    def __init__(self, routes=None, default=None):
        self.requests: list[httpx.Request] = []
        self.routes = routes or {}
        self.default = default if default is not None else []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v1/")
        reply = self.routes.get(f"{request.method} {path}", self.routes.get(path, self.default))
        if callable(reply):
            return reply(request)
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply)

    def calls(self, path: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"/api/v1/{path}" and (method is None or r.method == method)]


def body(request: httpx.Request):
    return json.loads(request.content) if request.content else None


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


async def _call(monkeypatch, recorder: Recorder, tool: str, args: dict):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    ctx = _credentials_var.set(CREDS)
    try:
        content, _ = await create_mcp_server().call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


# ---- TC1: connection check never echoes the token -------------------------------


async def test_connection_returns_ok_and_teams_without_leaking_token(monkeypatch):
    rec = Recorder({"accounts": [{"id": "acc1", "name": "My Team", "slug": "my-team"}]})
    result = await _call(monkeypatch, rec, "netlify_test_connection", {})
    assert result == {"ok": True, "teams": [{"id": "acc1", "name": "My Team", "slug": "my-team"}]}
    assert "token-123" not in json.dumps(result)
    assert rec.requests[0].headers["Authorization"] == "Bearer token-123"


# ---- TC3/TC4: get_site ------------------------------------------------------------


async def test_get_site_returns_core_fields(monkeypatch):
    rec = Recorder({"sites/site1": {"id": "site1", "name": "example", "url": "https://example.netlify.app", "ssl_url": "https://example.netlify.app"}})
    result = await _call(monkeypatch, rec, "netlify_get_site", {"site_id": "site1"})
    assert result["id"] == "site1" and result["name"] == "example"
    assert result["url"] == "https://example.netlify.app" and result["ssl_url"] == "https://example.netlify.app"


async def test_get_site_unknown_id_returns_not_found(monkeypatch):
    rec = Recorder({"sites/missing": lambda r: httpx.Response(404, json={"code": 404, "message": "Site not found"})})
    result = await _call(monkeypatch, rec, "netlify_get_site", {"site_id": "missing"})
    assert result["error"]["code"] == "not_found"
    assert "Site not found" in result["error"]["message"]


# ---- TC5/TC6: delete_site confirm gate ---------------------------------------------


async def test_delete_site_without_confirm_is_refused(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "netlify_delete_site", {"site_id": "site1"})
    assert result == {"deleted": False, "reason": "confirm_required"}
    assert rec.requests == []


async def test_delete_site_with_confirm_then_get_returns_not_found(monkeypatch):
    rec = Recorder({"DELETE sites/site1": httpx.Response(204), "GET sites/site1": lambda r: httpx.Response(404, json={"code": 404, "message": "Site not found"})})
    delete_result = await _call(monkeypatch, rec, "netlify_delete_site", {"site_id": "site1", "confirm": True})
    assert delete_result == {"deleted": True}
    get_result = await _call(monkeypatch, rec, "netlify_get_site", {"site_id": "site1"})
    assert get_result["error"]["code"] == "not_found"


# ---- TC7: list_deploys newest-first with state -------------------------------------


async def test_list_deploys_returns_newest_first_with_state(monkeypatch):
    deploys = [
        {"id": "d2", "state": "ready", "branch": "main", "created_at": "2026-11-02T00:00:00Z"},
        {"id": "d1", "state": "ready", "branch": "main", "created_at": "2026-11-01T00:00:00Z"},
    ]
    rec = Recorder({"sites/site1/deploys": deploys})
    result = await _call(monkeypatch, rec, "netlify_list_deploys", {"site_id": "site1"})
    assert [d["id"] for d in result["items"]] == ["d2", "d1"]
    assert all("state" in d for d in result["items"])


# ---- TC8/TC9: restore_deploy confirm gate + success --------------------------------


async def test_restore_deploy_without_confirm_is_refused(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "netlify_restore_deploy", {"site_id": "site1", "deploy_id": "d1"})
    assert result == {"restored": False, "reason": "confirm_required"}
    assert rec.requests == []


async def test_restore_deploy_with_confirm_becomes_live(monkeypatch):
    rec = Recorder({"POST sites/site1/deploys/d1/restore": {"id": "d1", "state": "ready", "branch": "main"}})
    result = await _call(monkeypatch, rec, "netlify_restore_deploy", {"site_id": "site1", "deploy_id": "d1", "confirm": True})
    assert result == {"restored": True, "deploy": {"id": "d1", "state": "ready", "branch": "main"}}
    assert rec.calls("sites/site1/deploys/d1/restore", "POST")


# ---- TC10: deploy-list rate limiting ------------------------------------------------


async def test_list_deploys_rate_limited_returns_retryable_error(monkeypatch):
    rec = Recorder({"GET sites/site1/deploys": lambda r: httpx.Response(429, json={"code": 429, "message": "Rate limited"})})
    result = await _call(monkeypatch, rec, "netlify_list_deploys", {"site_id": "site1"})
    assert result["error"] == {"code": "rate_limited", "message": "Netlify returned HTTP 429 for sites/site1/deploys: Rate limited", "retryable": True}


# ---- TC11: secret env vars are passed through exactly, never re-masked ------------


async def test_secret_env_var_value_is_masked_outside_dev_context(monkeypatch):
    upstream_shape = {
        "key": "DB_PASSWORD",
        "is_secret": True,
        "values": [{"context": "production", "value": "***", "context_parameter": None}],
    }
    rec = Recorder({"sites/site1/env": [upstream_shape]})
    result = await _call(monkeypatch, rec, "netlify_list_site_env_vars", {"site_id": "site1"})
    assert result["items"] == [upstream_shape]  # passed through unchanged, no extra masking applied


# ---- TC12/TC13/TC14: env var set/delete/scoping ------------------------------------


async def test_set_env_var_value_updates_only_target_context(monkeypatch):
    rec = Recorder({"PATCH accounts/acc1/env/FOO": {"key": "FOO", "values": [{"context": "production", "value": "bar"}]}})
    result = await _call(monkeypatch, rec, "netlify_set_env_var_value", {"account_id": "acc1", "key": "FOO", "value": "bar", "context": "production"})
    assert body(rec.requests[0]) == {"context": "production", "value": "bar"}
    assert result["values"][0] == {"context": "production", "value": "bar"}


async def test_delete_env_var_without_confirm_is_refused(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "netlify_delete_env_var", {"account_id": "acc1", "key": "FOO"})
    assert result == {"deleted": False, "reason": "confirm_required"}
    assert rec.requests == []


async def test_create_env_var_with_site_id_is_site_scoped(monkeypatch):
    rec = Recorder({"POST accounts/acc1/env": {"key": "FOO", "values": []}})
    await _call(
        monkeypatch,
        rec,
        "netlify_create_env_var",
        {"account_id": "acc1", "key": "FOO", "values": [{"context": "production", "value": "bar"}], "site_id": "site1"},
    )
    assert rec.requests[0].url.params["site_id"] == "site1"
    assert body(rec.requests[0]) == {
        "key": "FOO",
        "values": [{"context": "production", "value": "bar"}],
        "scopes": ["builds", "functions", "runtime", "post-processing"],
        "is_secret": False,
    }


# ---- TC15/TC16/TC17: forms and submissions ------------------------------------------


async def test_list_form_submissions_returns_fields_newest_first(monkeypatch):
    submissions = [
        {"id": "s2", "form_id": "f1", "data": {"email": "b@example.com"}, "created_at": "2026-11-02T00:00:00Z"},
        {"id": "s1", "form_id": "f1", "data": {"email": "a@example.com"}, "created_at": "2026-11-01T00:00:00Z"},
    ]
    rec = Recorder({"forms/f1/submissions": submissions})
    result = await _call(monkeypatch, rec, "netlify_list_form_submissions", {"form_id": "f1"})
    assert [s["id"] for s in result["items"]] == ["s2", "s1"]
    assert all("data" in s and "created_at" in s for s in result["items"])


async def test_mark_submission_spam_then_ham_toggles_state(monkeypatch):
    rec = Recorder({"PUT submissions/s1/spam": {}, "PUT submissions/s1/ham": {}})
    spam = await _call(monkeypatch, rec, "netlify_mark_submission_spam", {"submission_id": "s1"})
    ham = await _call(monkeypatch, rec, "netlify_mark_submission_ham", {"submission_id": "s1"})
    assert spam == {"submission_id": "s1", "state": "spam"}
    assert ham == {"submission_id": "s1", "state": "verified"}


async def test_delete_form_without_confirm_is_refused(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "netlify_delete_form", {"site_id": "site1", "form_id": "f1"})
    assert result == {"deleted": False, "reason": "confirm_required"}
    assert rec.requests == []


# ---- TC18/TC19/TC20/TC21: DNS -------------------------------------------------------


async def test_list_and_get_dns_records_return_record_fields(monkeypatch):
    records = [{"id": "r1", "type": "A", "hostname": "www", "value": "1.2.3.4"}]
    rec = Recorder({"dns_zones/zone1/records": records, "dns_zones/zone1/records/r1": records[0]})
    listed = await _call(monkeypatch, rec, "netlify_list_dns_records", {"zone_id": "zone1"})
    got = await _call(monkeypatch, rec, "netlify_get_dns_record", {"zone_id": "zone1", "record_id": "r1"})
    assert listed["items"][0]["type"] == "A" and listed["items"][0]["hostname"] == "www"
    assert got["type"] == "A" and got["value"] == "1.2.3.4"
    # not paginated: no page/per_page/has_more fields
    assert "page" not in listed and "has_more" not in listed


async def test_get_dns_zone_unknown_id_returns_not_found(monkeypatch):
    rec = Recorder({"dns_zones/missing": lambda r: httpx.Response(404, json={"code": 404, "message": "Zone not found"})})
    result = await _call(monkeypatch, rec, "netlify_get_dns_zone", {"zone_id": "missing"})
    assert result["error"]["code"] == "not_found"


async def test_delete_dns_zone_without_confirm_is_refused(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "netlify_delete_dns_zone", {"zone_id": "zone1"})
    assert result == {"deleted": False, "reason": "confirm_required"}
    assert rec.requests == []


async def test_create_then_delete_dns_record_round_trip(monkeypatch):
    created = {"id": "r1", "type": "TXT", "hostname": "_test", "value": "hello"}
    rec = Recorder(
        {
            "POST dns_zones/zone1/records": created,
            "DELETE dns_zones/zone1/records/r1": httpx.Response(204),
            "GET dns_zones/zone1/records/r1": lambda r: httpx.Response(404, json={"code": 404, "message": "Record not found"}),
        }
    )
    create_result = await _call(monkeypatch, rec, "netlify_create_dns_record", {"zone_id": "zone1", "type": "TXT", "hostname": "_test", "value": "hello"})
    assert create_result == created
    assert body(rec.calls("dns_zones/zone1/records", "POST")[0])["ttl"] == 3600
    delete_result = await _call(monkeypatch, rec, "netlify_delete_dns_record", {"zone_id": "zone1", "record_id": "r1", "confirm": True})
    assert delete_result == {"deleted": True}
    get_result = await _call(monkeypatch, rec, "netlify_get_dns_record", {"zone_id": "zone1", "record_id": "r1"})
    assert get_result["error"]["code"] == "not_found"


# ---- TC23/TC24: error mapping -------------------------------------------------------


async def test_error_mapping_422_returns_invalid_argument_envelope(monkeypatch):
    rec = Recorder({"POST sites": lambda r: httpx.Response(422, json={"code": 422, "message": "name has already been taken"})})
    result = await _call(monkeypatch, rec, "netlify_create_site", {"name": "taken-name"})
    assert result["error"]["code"] == "invalid_argument"
    assert "name has already been taken" in result["error"]["message"]
    assert result["error"]["retryable"] is False


async def test_error_mapping_timeout_returns_upstream_error_envelope(monkeypatch):
    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    rec = Recorder({"sites": raise_timeout})
    result = await _call(monkeypatch, rec, "netlify_list_sites", {})
    assert result["error"]["code"] == "upstream_error"
    assert result["error"]["retryable"] is True
