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
"""Netlify deploys: history and rollback.

netlify_restore_deploy is the only "change what's live" tool in this version (see
the design's Non-goals: a from-file deploy upload is a multi-step protocol out of
scope for a single JSON-RPC call).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..api_client import NetlifyClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    ClientFactory,
    Confirm,
    DeployId,
    Page,
    PerPage,
    SiteId,
    compact,
    list_page,
    not_confirmed,
    run_tool,
)


def _deploy_fields(deploy: Any) -> Any:
    if not isinstance(deploy, dict):
        return deploy
    return compact(
        {
            "id": deploy.get("id"),
            "state": deploy.get("state"),
            "branch": deploy.get("branch"),
            "commit_ref": deploy.get("commit_ref"),
            "deploy_url": deploy.get("deploy_url"),
            "error_message": deploy.get("error_message"),
            "created_at": deploy.get("created_at"),
            "deploy_time": deploy.get("deploy_time"),
            "summary": deploy.get("summary"),
        }
    )


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_deploys(site_id: SiteId, page: Page = None, per_page: PerPage = None) -> str:
        """List a site's deploy history, newest first, with each deploy's build state."""

        async def action(client: NetlifyClient) -> dict:
            result = await list_page(client, f"sites/{site_id}/deploys", {}, page, per_page)
            result["items"] = [_deploy_fields(d) for d in result["items"]]
            return result

        return await run_tool("netlify_list_deploys", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_get_deploy(site_id: SiteId, deploy_id: DeployId) -> str:
        """Get one deploy's build state, timestamps, and the commit/branch that produced it.

        An unknown deploy_id returns a not_found error, not an exception.
        """

        async def action(client: NetlifyClient) -> Any:
            return _deploy_fields(await client.get(f"sites/{site_id}/deploys/{deploy_id}"))

        return await run_tool("netlify_get_deploy", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_restore_deploy(site_id: SiteId, deploy_id: DeployId, confirm: Confirm = None) -> str:
        """Roll a site back to a previous deploy, making it the live production deploy.

        Changes what the site's visitors see; needs confirm: true. Only when the user
        explicitly asks. Subject to Netlify's deploy-specific rate limit (3/minute).
        """

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("restored")
            deploy = await client.post(f"sites/{site_id}/deploys/{deploy_id}/restore")
            return {"restored": True, "deploy": _deploy_fields(deploy)}

        return await run_tool("netlify_restore_deploy", client_factory, action)
