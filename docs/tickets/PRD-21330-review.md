# PRD-21330 · Code review

Status: frozen @ 2a9af51

## Round 1 · 2026-11-05 · reviewed dev/PRD-21330 @ 2a9af51 (base origin/main @ 63943ee)

Verdict: approved

### Scope

New repo `MSPbotsAIFramework/netlify-mcp`. Base is the admin-created README-only scaffold
(`63943ee`, no `src/`); `git diff origin/main...dev/PRD-21330` is the entire implementation
(32 files, +4228/-2). Reviewed against the design (`docs/tickets/PRD-21330.md`), the 14 ACs,
the 26-case `docs/tickets/PRD-21330.ac.json`, the Self-test section, and `references/REVIEW.md`.

### Independent verification performed

- `uv sync` — resolves cleanly from the committed `uv.lock`.
- `uv run pytest -q` — **137 passed**, 0 failed (matches the `[DEV]` stub exactly).
- `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` — no output, no
  Chinese anywhere in the repo.
- README "MSPbots Connector" section vs
  `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` — byte-identical
  (diffed with trailing-blank-line normalization on both sides).
- Live smoke on a clean port: `GET /health` → `200 {"status":"ok"}`; `POST /mcp` with no
  `X-Netlify-Token` → `401` naming the header; `initialize` → `tools/list` returns all 31 tool
  names, stateless (no session id); `tools/call netlify_test_connection` with a placeholder token
  → a structured `{"error":{"code":"unauthorized",...}}` envelope, not a crash or raw exception.
  (First attempt on port 8911 hit a stale, unrelated process left listening from another ticket —
  confirmed via the bind-failure in this run's own server log and `ss -ltnp`, then re-run on a
  free port; not a defect in this repo.)
- Manually re-read every tool in `tools/{connection,sites,deploys,env_vars,forms,dns}.py` against
  the Data & API contract table (all 31 tool signatures, HTTP verbs, and response shapes match);
  confirmed `netlify_restore_deploy` uses `POST .../restore` as the Handoff section records, and
  every destructive tool (8 of 31: site/env-var/form/submission/DNS-zone/DNS-record delete, deploy
  restore) is gated on `confirm is True` before any request reaches Netlify.
- `pyproject.toml` / `Dockerfile` reviewed against SOP §14: non-root production user, `curl`
  installed, `EXPOSE 8080`, `HEALTHCHECK`, `uv.lock` committed, license (Apache-2.0) + `LICENSE` +
  `NOTICE` present.

### Findings

None (0 must-fix, 0 suggestions).

- Credentials: `X-Netlify-Token` is read only in `middleware.py`, carried in a `contextvars`
  value reset in `finally`, never logged (`NetlifyCredentials.__repr__` redacts it), never
  cached across requests — matches the SOP's three isolation rules.
- Error envelope: `api_client.classify_status` maps every status to one of the six fixed
  `code` values; `_common.run_tool` catches every exception type a tool can raise and always
  returns a string — verified no tool can leak an uncaught exception.
- Tests follow the design's own shape (`tools/list` snapshot, status-mapping table, pagination
  edge cases, concurrent-credential isolation) and match the Self-test's claimed 137 passed; no
  evidence of a test rewritten to fit the implementation.
- Reuse & cleanup: no unofficial third-party Netlify SDK added; new dependencies
  (`fastmcp`/`mcp[cli]`, `httpx`, `pydantic`, `pydantic-settings`, `uvicorn`, `starlette`) are all
  named and justified in the design's Reuse & cleanup / Option analysis sections — none
  undisclosed. No migrations in this track (MCP repo, no database).
- Scope: all 31 tools match the Change list and the Data & API contract exactly; nothing added
  or dropped relative to the design.

### Fixes

N/A — no must-fix in Round 1.
