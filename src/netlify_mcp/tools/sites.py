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
"""Netlify sites: list/get/create/update/delete."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NetlifyClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Confirm,
    Page,
    PerPage,
    SiteId,
    Text,
    compact,
    list_page,
    not_confirmed,
    run_tool,
)


def _site_fields(site: Any) -> Any:
    if not isinstance(site, dict):
        return site
    return compact(
        {
            "id": site.get("id"),
            "name": site.get("name"),
            "url": site.get("url"),
            "admin_url": site.get("admin_url"),
            "ssl_url": site.get("ssl_url"),
            "custom_domain": site.get("custom_domain"),
            "state": site.get("state"),
            "account_slug": site.get("account_slug"),
            "created_at": site.get("created_at"),
            "updated_at": site.get("updated_at"),
            "build_settings": site.get("build_settings"),
        }
    )


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_sites(page: Page = None, per_page: PerPage = None) -> str:
        """List sites with their id, name, URLs, SSL/custom-domain state and build settings."""

        async def action(client: NetlifyClient) -> dict:
            result = await list_page(client, "sites", {}, page, per_page)
            result["items"] = [_site_fields(s) for s in result["items"]]
            return result

        return await run_tool("netlify_list_sites", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_get_site(site_id: SiteId) -> str:
        """Get one site's id, name, URLs, SSL/custom-domain state and build settings.

        An unknown site_id returns a not_found error, not an exception.
        """

        async def action(client: NetlifyClient) -> Any:
            return _site_fields(await client.get(f"sites/{site_id}"))

        return await run_tool("netlify_get_site", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def netlify_create_site(
        name: Text = None,
        account_slug: Annotated[
            str | None, Field(description="Team slug to create the site under; defaults to the token owner's personal team.")
        ] = None,
        custom_domain: Text = None,
    ) -> str:
        """Create a new plain (non-git-linked) site. Only when the user explicitly asks.

        Netlify assigns a random subdomain name when name is omitted, so repeated calls
        create distinct sites -- this tool is not idempotent.
        """

        async def action(client: NetlifyClient) -> Any:
            body = compact({"name": name, "custom_domain": custom_domain})
            params = compact({"account_slug": account_slug})
            return _site_fields(await client.post("sites", body, params=params))

        return await run_tool("netlify_create_site", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def netlify_update_site(
        site_id: SiteId,
        name: Text = None,
        custom_domain: Text = None,
        force_ssl: Annotated[bool | None, Field(description="Force HTTPS for this site.")] = None,
    ) -> str:
        """Change a site's name, custom domain, or forced-SSL setting; only the fields given change.

        Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            body = compact({"name": name, "custom_domain": custom_domain, "force_ssl": force_ssl})
            if not body:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return _site_fields(await client.patch(f"sites/{site_id}", body))

        return await run_tool("netlify_update_site", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_site(site_id: SiteId, confirm: Confirm = None) -> str:
        """Permanently delete a site. Irreversible; needs confirm: true. Only when explicitly asked."""

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            await client.delete(f"sites/{site_id}")
            return {"deleted": True}

        return await run_tool("netlify_delete_site", client_factory, action)
