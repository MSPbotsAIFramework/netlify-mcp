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
"""DNS zones and records."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NetlifyClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    ClientFactory,
    Confirm,
    Page,
    PerPage,
    RecordId,
    Text,
    ZoneId,
    compact,
    list_page,
    not_confirmed,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_dns_zones(page: Page = None, per_page: PerPage = None) -> str:
        """List DNS zones in the caller's account."""

        async def action(client: NetlifyClient) -> dict:
            return await list_page(client, "dns_zones", {}, page, per_page)

        return await run_tool("netlify_list_dns_zones", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_get_dns_zone(zone_id: ZoneId) -> str:
        """Get one DNS zone's name, account and name servers. An unknown zone_id returns not_found."""

        async def action(client: NetlifyClient) -> Any:
            return await client.get(f"dns_zones/{zone_id}")

        return await run_tool("netlify_get_dns_zone", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def netlify_create_dns_zone(
        name: Annotated[str, Field(description="Zone (domain) name, e.g. example.com.", min_length=1)],
        account_slug: Text = None,
        site_id: Annotated[str | None, Field(description="Site to link this zone to.")] = None,
    ) -> str:
        """Create a DNS zone for a domain. Only when the user explicitly asks; not idempotent."""

        async def action(client: NetlifyClient) -> Any:
            body = compact({"name": name, "account_slug": account_slug, "site_id": site_id})
            return await client.post("dns_zones", body)

        return await run_tool("netlify_create_dns_zone", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_dns_zone(zone_id: ZoneId, confirm: Confirm = None) -> str:
        """Permanently delete a DNS zone and every record in it. Irreversible; needs confirm: true.

        Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            await client.delete(f"dns_zones/{zone_id}")
            return {"deleted": True}

        return await run_tool("netlify_delete_dns_zone", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_dns_records(zone_id: ZoneId) -> str:
        """List every record in a DNS zone. Not paginated by Netlify's API for this endpoint."""

        async def action(client: NetlifyClient) -> dict:
            items = await client.get(f"dns_zones/{zone_id}/records")
            return {"items": items if isinstance(items, list) else []}

        return await run_tool("netlify_list_dns_records", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_get_dns_record(zone_id: ZoneId, record_id: RecordId) -> str:
        """Get one DNS record's type, hostname and value. An unknown record_id returns not_found."""

        async def action(client: NetlifyClient) -> Any:
            return await client.get(f"dns_zones/{zone_id}/records/{record_id}")

        return await run_tool("netlify_get_dns_record", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def netlify_create_dns_record(
        zone_id: ZoneId,
        type: Annotated[str, Field(description="Record type, e.g. A, AAAA, CNAME, TXT, MX, SRV, NS, CAA.", min_length=1)],
        hostname: Annotated[str, Field(description="Record hostname/subdomain.", min_length=1)],
        value: Annotated[str, Field(description="Record value.", min_length=1)],
        ttl: Annotated[int, Field(description="Time to live in seconds.", ge=1)] = 3600,
        priority: Annotated[int | None, Field(description="MX/SRV priority; only meaningful for those record types.")] = None,
        weight: Annotated[int | None, Field(description="SRV weight; only meaningful for SRV records.")] = None,
        port: Annotated[int | None, Field(description="SRV port; only meaningful for SRV records.")] = None,
    ) -> str:
        """Add a DNS record to a zone. Only when the user explicitly asks; not idempotent.

        priority/weight/port are only meaningful for MX/SRV records and are otherwise omitted.
        """

        async def action(client: NetlifyClient) -> Any:
            body = compact(
                {"type": type, "hostname": hostname, "value": value, "ttl": ttl, "priority": priority, "weight": weight, "port": port}
            )
            return await client.post(f"dns_zones/{zone_id}/records", body)

        return await run_tool("netlify_create_dns_record", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_dns_record(zone_id: ZoneId, record_id: RecordId, confirm: Confirm = None) -> str:
        """Permanently delete a DNS record. Irreversible; needs confirm: true. Only when explicitly asked."""

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            await client.delete(f"dns_zones/{zone_id}/records/{record_id}")
            return {"deleted": True}

        return await run_tool("netlify_delete_dns_record", client_factory, action)
