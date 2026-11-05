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
"""FastMCP factory: builds the server and registers every tool module."""

from mcp.server.transport_security import TransportSecuritySettings

from ._arguments import EnvelopeFastMCP
from .config import Settings
from .middleware import get_client_from_context

INSTRUCTIONS = (
    "Netlify hosts and deploys static sites and serverless functions. One Netlify "
    "personal access token can act on one or more teams (accounts).\n"
    "Usage:\n"
    "- Discover teams first: netlify_list_accounts; account_id feeds the "
    "environment-variable and DNS-zone tools below.\n"
    "- Sites: netlify_list_sites -> netlify_get_site. netlify_restore_deploy rolls "
    "a site back to an earlier deploy; there is no tool to push a new deploy from "
    "a file bundle in this version.\n"
    "- Environment variables are two-level: team-wide "
    "(netlify_list_account_env_vars) or one site (netlify_list_site_env_vars, or "
    "pass site_id to the account-level tools). Secret values are masked by "
    "Netlify itself for every context but dev.\n"
    "- Lists page with page + per_page; has_more/next_page say whether to page "
    "on (Netlify has no total count in any list response).\n"
    "Create and update tools change data: call them only when the user "
    "explicitly asks, with the exact values given. Delete and restore tools are "
    "destructive and need confirm: true, set only after the user approved that "
    "exact action."
)


def create_mcp_server(settings: Settings | None = None) -> EnvelopeFastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="netlify-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory = get_client_from_context

    from .tools import connection, deploys, dns, env_vars, forms, sites

    for module in (connection, sites, deploys, env_vars, forms, dns):
        module.register(mcp, client_factory)

    return mcp
