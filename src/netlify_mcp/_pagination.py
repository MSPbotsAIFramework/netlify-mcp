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
"""Parses the RFC 5988 ``Link`` response header into ``{has_more, next_page}``.

Unlike every other vendor API this fleet's MCPs wrap (an in-body count or cursor),
Netlify signals "more pages exist" only through this HTTP response header, e.g.:

    Link: <https://api.netlify.com/api/v1/sites?page=3&per_page=50>; rel="next",
          <https://api.netlify.com/api/v1/sites?page=9&per_page=50>; rel="last"

A missing or malformed header is treated as "no more pages" rather than raising,
since a parsing hiccup must never turn into a crashed tool call.
"""

import re
from urllib.parse import parse_qs, urlparse

# One <url>; rel="name" segment. Netlify (and RFC 5988 generally) separates multiple
# segments with a comma; the quotes around rel are optional per the RFC.
_LINK_SEGMENT = re.compile(r'<([^>]*)>\s*;\s*rel="?([^";,]*)"?', re.IGNORECASE)


def parse_link_header(header_value: str | None) -> dict:
    """``{"has_more": bool, "next_page": int | None}`` from a ``Link`` header value."""
    if not header_value or not header_value.strip():
        return {"has_more": False, "next_page": None}
    try:
        for url, rel in _LINK_SEGMENT.findall(header_value):
            if rel.strip().lower() != "next":
                continue
            page_values = parse_qs(urlparse(url).query).get("page", [])
            page = page_values[0] if page_values else None
            next_page = int(page) if page is not None and page.lstrip("-").isdigit() else None
            return {"has_more": True, "next_page": next_page}
    except Exception:  # noqa: BLE001 - a malformed header must never raise
        return {"has_more": False, "next_page": None}
    return {"has_more": False, "next_page": None}
