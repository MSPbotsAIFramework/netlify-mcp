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
"""Shared argument types, the pagination envelope, confirmation and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from .._pagination import parse_link_header
from ..api_client import NetlifyClient, NetlifyError
from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

logger = logging.getLogger("netlify_mcp.tools")

ClientFactory = Callable[[], NetlifyClient | None]

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITES_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured", "Netlify credentials are missing for this request (X-Netlify-Token).", False
)

# Netlify's own resource ids are plain strings (not necessarily numeric), unlike
# Hudu's integer ids -- so these are str, not the RecordId=int pattern.
SiteId = Annotated[str, Field(description="Netlify site id.", min_length=1)]
AccountId = Annotated[str, Field(description="Netlify team/account id.", min_length=1)]
DeployId = Annotated[str, Field(description="Netlify deploy id.", min_length=1)]
FormId = Annotated[str, Field(description="Netlify form id.", min_length=1)]
SubmissionId = Annotated[str, Field(description="Netlify form submission id.", min_length=1)]
ZoneId = Annotated[str, Field(description="Netlify DNS zone id.", min_length=1)]
RecordId = Annotated[str, Field(description="Netlify DNS record id.", min_length=1)]

Page = Annotated[int | None, Field(description="Page number, from 1 (default 1).", ge=1)]
PerPage = Annotated[
    int | None,
    Field(description=f"Records per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).", ge=1, le=MAX_PAGE_SIZE),
]
Text = Annotated[str | None, Field(description="Value.")]
Confirm = Annotated[bool | None, Field(description="Must be true, set only after the user approved this exact action.")]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def not_confirmed(key: str) -> dict:
    return {key: False, "reason": "confirm_required"}


async def list_page(
    client: NetlifyClient,
    path: str,
    params: dict[str, Any],
    page: int | None,
    per_page: int | None,
) -> dict:
    """GET a Netlify list endpoint (a bare JSON array) and return {items, page, per_page, has_more, next_page}.

    Netlify never returns a count or cursor in the response body; has_more/next_page
    come only from the Link response header (see _pagination.py).
    """
    number = page or 1
    size = per_page or DEFAULT_PAGE_SIZE
    query = compact(params) | {"page": number, "per_page": size}
    data, response = await client.request("GET", path, params=query)
    items = data if isinstance(data, list) else []
    pagination = parse_link_header(response.headers.get("Link"))
    return {"items": items, "page": number, "per_page": size, **pagination}


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[NetlifyClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except NetlifyError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"done": True}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
