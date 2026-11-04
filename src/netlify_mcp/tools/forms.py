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
"""Forms and their submissions."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..api_client import NetlifyClient
from ._common import (
    DESTRUCTIVE,
    FormId,
    READ_ONLY,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Confirm,
    Page,
    PerPage,
    SiteId,
    SubmissionId,
    list_page,
    not_confirmed,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_forms(site_id: SiteId, page: Page = None, per_page: PerPage = None) -> str:
        """List a site's forms with their fields and submission counts."""

        async def action(client: NetlifyClient) -> dict:
            return await list_page(client, f"sites/{site_id}/forms", {}, page, per_page)

        return await run_tool("netlify_list_forms", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_form(site_id: SiteId, form_id: FormId, confirm: Confirm = None) -> str:
        """Permanently delete a form and its submissions. Irreversible; needs confirm: true.

        Only when the user explicitly asks.
        """

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            await client.delete(f"sites/{site_id}/forms/{form_id}")
            return {"deleted": True}

        return await run_tool("netlify_delete_form", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_site_submissions(site_id: SiteId, page: Page = None, per_page: PerPage = None) -> str:
        """List verified submissions across every form on a site, newest first."""

        async def action(client: NetlifyClient) -> dict:
            return await list_page(client, f"sites/{site_id}/submissions", {}, page, per_page)

        return await run_tool("netlify_list_site_submissions", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def netlify_list_form_submissions(form_id: FormId, page: Page = None, per_page: PerPage = None) -> str:
        """List one form's submissions with their field data, newest first."""

        async def action(client: NetlifyClient) -> dict:
            return await list_page(client, f"forms/{form_id}/submissions", {}, page, per_page)

        return await run_tool("netlify_list_form_submissions", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def netlify_mark_submission_spam(submission_id: SubmissionId) -> str:
        """Mark a form submission as spam. Only when the user explicitly asks."""

        async def action(client: NetlifyClient) -> Any:
            await client.put(f"submissions/{submission_id}/spam")
            return {"submission_id": submission_id, "state": "spam"}

        return await run_tool("netlify_mark_submission_spam", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def netlify_mark_submission_ham(submission_id: SubmissionId) -> str:
        """Mark a form submission as verified (not spam). Only when the user explicitly asks."""

        async def action(client: NetlifyClient) -> Any:
            await client.put(f"submissions/{submission_id}/ham")
            return {"submission_id": submission_id, "state": "verified"}

        return await run_tool("netlify_mark_submission_ham", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def netlify_delete_submission(submission_id: SubmissionId, confirm: Confirm = None) -> str:
        """Permanently delete a form submission. Irreversible; needs confirm: true. Only when explicitly asked."""

        async def action(client: NetlifyClient) -> Any:
            if confirm is not True:
                return not_confirmed("deleted")
            await client.delete(f"submissions/{submission_id}")
            return {"deleted": True}

        return await run_tool("netlify_delete_submission", client_factory, action)
