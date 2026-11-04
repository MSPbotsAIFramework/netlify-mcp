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
"""Per-request credential isolation: reads X-Netlify-Token, 401 when missing or empty."""

import contextvars
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import NetlifyClient, NetlifyCredentials

HEADER_TOKEN = "X-Netlify-Token"
REQUIRED_HEADERS = [HEADER_TOKEN]

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[NetlifyCredentials | None] = contextvars.ContextVar(
    "netlify_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("netlify_request_id", default="-")


def get_client_from_context() -> NetlifyClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return NetlifyClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


class CredentialsMiddleware:
    """Reads X-Netlify-Token on /mcp requests; 401 when missing or empty."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        token = _clean(request.headers.get(HEADER_TOKEN))
        if not token:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Missing header: {HEADER_TOKEN}",
                    "required_headers": REQUIRED_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(NetlifyCredentials(token))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)
