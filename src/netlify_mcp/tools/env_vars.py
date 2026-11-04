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
"""Environment variables: team (account) scoped, optionally narrowed to one site.

Mirrors Netlify's own two-level model directly (account_id required, site_id an
optional query parameter) rather than inventing a single "scope" enum -- see the
design's Decisions made by DEV01.
"""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NetlifyClient
from ._common import (
    AccountId,
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Confirm,
    SiteId,
    Text,
    compact,
    not_confirmed,
    run_tool,
)

DEFAULT_SCOPES = ["builds", "functions", "runtime", "post-processing"]
EnvVarKey = Annotated[str, Field(description="Environment variable name.", min_length=1)]
ScopedSiteId = Annotated[str | None, Field(description="Narrow to this one site instead of the whole team.")]
ScopeFilter = Annotated[str | None, Field(description="Filter by scope: builds, functions, runtime, or post-processing.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_site_env_vars(site_id: SiteId, context_name: Text = None, scope: ScopeFilter = None) -> str:
        """List one site's environment variables; secret values come back masked by Netlify itself."""

        async def action(client: NetlifyClient) -> dict:
            params = compact({"context_name": context_name, "scope": scope})
            items = await client.get(f"sites/{site_id}/env", params)
            return {"items": items if isinstance(items, list) else []}

        return await run_tool("netlify_list_site_env_vars", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_account_env_vars(
        account_id: AccountId, site_id: ScopedSiteId = None, context_name: Text = None, scope: ScopeFilter = None
    ) -> str:
        """List a team's environment variables, optionally narrowed to one site.

        Secret values come back masked by Netlify itself for every context but dev.
        """

        async def action(client: NetlifyClient) -> dict:
            params = compact({"site_id": site_id, "context_name": context_name, "scope": scope})
            items = await client.get(f"accounts/{account_id}/env", params)
            return {"items": items if isinstance(items, list) else []}

        return await run_tool("netlify_list_account_env_vars", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_get_env_var(account_id: AccountId, key: EnvVarKey, site_id: ScopedSiteId = None) -> str:
        """Get one environment variable's values across contexts; secret values come back masked.

        An unknown key returns a not_found error, not an exception.
        """

        async def action(client: NetlifyClient) -> Any:
            params = compact({"site_id": site_id})
            return await client.get(f"accounts/{account_id}/env/{key}", params)

        return await run_tool("netlify_get_env_var", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def netlify_create_env_var(
        account_id: AccountId,
        key: EnvVarKey,
        values: Annotated[
            list[dict],
            Field(description='Per-context values: [{"context": "production"|"deploy-preview"|"branch-deploy"|"dev", "value": str, "context_parameter": str | None}, ...].'),
        ],
        scopes: Annotated[list[str], Field(description="Which build phases see this variable.")] = DEFAULT_SCOPES,
        is_secret: Annotated[
            bool, Field(description="Hide the value after creation (Netlify masks it for every context but dev).")
        ] = False,
        site_id: ScopedSiteId = None,
    ) -> str:
        """Create an environment variable at the team level, or scoped to one site when site_id is given.

        Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            body = {"key": key, "values": values, "scopes": scopes, "is_secret": is_secret}
            params = compact({"site_id": site_id})
            return await client.post(f"accounts/{account_id}/env", body, params=params)

        return await run_tool("netlify_create_env_var", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def netlify_set_env_var_value(
        account_id: AccountId,
        key: EnvVarKey,
        value: Annotated[str, Field(description="New value for this context.")],
        context: Annotated[
            str, Field(description='Context to change: "production", "deploy-preview", "branch-deploy", "dev", or "all".')
        ] = "all",
        context_parameter: Text = None,
        site_id: ScopedSiteId = None,
    ) -> str:
        """Upsert one context's value for an environment variable, leaving other contexts unchanged.

        Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            body = compact({"context": context, "value": value, "context_parameter": context_parameter})
            params = compact({"site_id": site_id})
            return await client.patch(f"accounts/{account_id}/env/{key}", body, params=params)

        return await run_tool("netlify_set_env_var_value", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_env_var(account_id: AccountId, key: EnvVarKey, site_id: ScopedSiteId = None, confirm: Confirm = None) -> str:
        """Permanently delete an environment variable, every context at once. Irreversible.

        Needs confirm: true. Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            params = compact({"site_id": site_id})
            await client.delete(f"accounts/{account_id}/env/{key}", params)
            return {"deleted": True}

        return await run_tool("netlify_delete_env_var", client_factory, action)
