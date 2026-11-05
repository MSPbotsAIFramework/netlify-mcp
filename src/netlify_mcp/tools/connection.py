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
"""Connection check and team/account discovery."""

from mcp.server.fastmcp import FastMCP

from ..api_client import NetlifyClient
from ._common import READ_ONLY, ClientFactory, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_test_connection() -> str:
        """Check the Netlify token is valid and list the team(s) it can act on."""

        async def action(client: NetlifyClient) -> dict:
            accounts = await client.get("accounts")
            teams = [
                {"id": a.get("id"), "name": a.get("name"), "slug": a.get("slug")}
                for a in (accounts if isinstance(accounts, list) else [])
            ]
            return {"ok": True, "teams": teams}

        return await run_tool("netlify_test_connection", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_accounts() -> str:
        """List the teams (accounts) this Netlify token can act on, with their ids and slugs."""

        async def action(client: NetlifyClient) -> dict:
            accounts = await client.get("accounts")
            items = accounts if isinstance(accounts, list) else []
            return {
                "accounts": [
                    {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "slug": a.get("slug"),
                        "type": a.get("type"),
                        "created_at": a.get("created_at"),
                    }
                    for a in items
                ]
            }

        return await run_tool("netlify_list_accounts", client_factory, action)
