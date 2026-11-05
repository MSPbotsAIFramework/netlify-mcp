# Netlify MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Netlify](https://www.netlify.com) API
(v1), the web-hosting and deployment platform. It lets an AI agent read sites, deploy history,
environment variables, form submissions and DNS zones/records and, on explicit request, create
and update records, roll a site back to a previous deploy, and (with confirmation) delete them.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as an HTTP header and are
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Netlify-Token` | Yes | string | none | - | Netlify personal access token | `nfp_xxx` |

Where to get it: in Netlify, go to **User settings → Applications → Personal access tokens** and
create a new token. The token grants access to every team the account belongs to; there is no
per-resource scoping on Netlify's side, so give the agent a token for the account you want it to
act on.

How the token is sent to Netlify: every call goes to `https://api.netlify.com/api/v1/...` with
`Authorization: Bearer <token>`.

A request to `/mcp` without the header (or with an empty value) gets HTTP 401 naming it.

## Tools

All tools return a JSON string. List tools take `page` and `per_page` (default 50, max 100) and
return `{items, page, per_page, has_more, next_page}` -- there is no `count` field, because
Netlify never returns a total result count in any list response body; `has_more`/`next_page` are
parsed from the response's `Link` header instead. `netlify_list_dns_records` is the one
exception: Netlify does not paginate that endpoint, so it returns `{items}` only. **write** marks
tools that change data; **confirm** marks destructive tools, which also need `confirm: true`.

| Area | Tools |
|---|---|
| Connection | `netlify_test_connection`, `netlify_list_accounts` |
| Sites | `netlify_list_sites`, `netlify_get_site` (**site_id**); **write**: `netlify_create_site`, `netlify_update_site` (**site_id**); **confirm**: `netlify_delete_site` (**site_id**) |
| Deploys | `netlify_list_deploys` (**site_id**), `netlify_get_deploy` (**site_id**, **deploy_id**); **confirm**: `netlify_restore_deploy` (**site_id**, **deploy_id**) |
| Environment variables | `netlify_list_site_env_vars` (**site_id**), `netlify_list_account_env_vars` (**account_id**), `netlify_get_env_var` (**account_id**, **key**); **write**: `netlify_create_env_var` (**account_id**, **key**, **values**), `netlify_set_env_var_value` (**account_id**, **key**, **value**); **confirm**: `netlify_delete_env_var` (**account_id**, **key**) |
| Forms | `netlify_list_forms` (**site_id**), `netlify_list_site_submissions` (**site_id**), `netlify_list_form_submissions` (**form_id**); **write**: `netlify_mark_submission_spam` (**submission_id**), `netlify_mark_submission_ham` (**submission_id**); **confirm**: `netlify_delete_form` (**site_id**, **form_id**), `netlify_delete_submission` (**submission_id**) |
| DNS | `netlify_list_dns_zones`, `netlify_get_dns_zone` (**zone_id**), `netlify_list_dns_records` (**zone_id**), `netlify_get_dns_record` (**zone_id**, **record_id**); **write**: `netlify_create_dns_zone` (**name**), `netlify_create_dns_record` (**zone_id**, **type**, **hostname**, **value**); **confirm**: `netlify_delete_dns_zone` (**zone_id**), `netlify_delete_dns_record` (**zone_id**, **record_id**) |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "not_found", "message": "Netlify returned HTTP 404 for sites/abc123: Site not found", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. Reads are retried with backoff on 429, 5xx and network errors;
writes only on 429. Netlify allows about 500 requests/minute generally, but deploy-related
endpoints (`netlify_restore_deploy`, `netlify_list_deploys`) are limited to 3/minute and 100/day.

## Run locally

```bash
uv sync
uv run python -m netlify_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t netlify-mcp:dev .
docker run --rm -p 8080:8080 netlify-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Netlify-Token: your-netlify-token" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# a team's sites
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Netlify-Token: your-netlify-token" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"netlify_list_sites","arguments":{}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **No sandbox environment.** Unlike some vendors wrapped by this fleet (e.g. Plaid's sandbox),
  Netlify has no simulated institution. Tools beyond `netlify_test_connection` /
  `netlify_list_accounts` are unit-tested against a stubbed API only; exercising them against a
  real Netlify team is listed as "needs a real vendor account" per ticket PRD-21330's test plan,
  and is not a blocker to shipping this version.
- **Pagination is header-driven.** Netlify signals "more pages exist" only through the HTTP
  `Link` response header (`rel="next"`), never an in-body count or cursor. `_pagination.py`
  parses it; a missing or malformed header is treated as "no more pages" rather than raising.
- **`netlify_list_dns_records` is not paginated.** Netlify's documented API for this endpoint
  takes no `page`/`per_page` parameters, so the tool omits them and returns `{items}` only.
- **`netlify_restore_deploy` calls `POST .../restore`.** Netlify's getting-started docs
  (`docs.netlify.com/api/get-started/`) and its OpenAPI reference (`open-api.netlify.com`)
  disagreed on `POST` vs `PUT` for this endpoint at design time; `POST` was kept per the primary
  getting-started doc. Confirm against the live API with a real account before relying on it.
- **Environment variables follow Netlify's own two-level model exactly**: every account-scoped
  tool takes `account_id` (required) and an optional `site_id` query parameter, rather than a
  custom "scope" abstraction.
- **Secret masking is inherited, not reimplemented.** Netlify itself never returns an
  `is_secret: true` value in clear text for any context but `dev`; this server passes that
  response through unchanged and does not attempt to mask or unmask it.
- **Deletes and the deploy restore need confirmation.** Every destructive tool takes
  `confirm: true` and otherwise returns `{"<verb>ed": false, "reason": "confirm_required"}`.
- **Tool count (31).** Larger than this fleet's usual guideline (≤ 20) because it spans five
  independent Netlify resource groups (sites, deploys, environment variables, forms, DNS), each a
  thin single-header-credential wrapper, matching the precedent already accepted for Box, Plaid
  and Figma (same architecture, same tool-count shape, per the design's Effort & breakdown).

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
