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
"""Link-header parsing (TC26): present / absent / malformed.

Netlify is the one vendor in this fleet that signals "more pages exist" only
through this HTTP response header, never an in-body count or cursor.
"""

from netlify_mcp._pagination import parse_link_header


def test_next_page_is_parsed_from_the_link_header():
    header = (
        '<https://api.netlify.com/api/v1/sites?page=3&per_page=50>; rel="next", '
        '<https://api.netlify.com/api/v1/sites?page=9&per_page=50>; rel="last"'
    )
    assert parse_link_header(header) == {"has_more": True, "next_page": 3}


def test_rel_without_quotes_is_also_parsed():
    header = "<https://api.netlify.com/api/v1/sites?page=2>; rel=next"
    assert parse_link_header(header) == {"has_more": True, "next_page": 2}


def test_no_header_means_no_more_pages():
    assert parse_link_header(None) == {"has_more": False, "next_page": None}
    assert parse_link_header("") == {"has_more": False, "next_page": None}


def test_header_with_only_prev_or_last_means_no_more_pages():
    header = '<https://api.netlify.com/api/v1/sites?page=1>; rel="prev"'
    assert parse_link_header(header) == {"has_more": False, "next_page": None}


def test_malformed_header_does_not_raise():
    for malformed in ("not a link header at all", "<no-rel-here>", "<>;rel=", ";;;garbage;;;"):
        assert parse_link_header(malformed) == {"has_more": False, "next_page": None}


def test_next_link_with_non_numeric_or_missing_page_has_more_but_no_page_number():
    header = '<https://api.netlify.com/api/v1/sites?cursor=abc>; rel="next"'
    assert parse_link_header(header) == {"has_more": True, "next_page": None}


def test_link_header_parsing_next_absent_and_malformed():
    """TC26: present (rel=next with page=3) / absent / malformed, in one assertion."""
    present = '<https://api.netlify.com/api/v1/sites?page=3&per_page=50>; rel="next"'
    assert parse_link_header(present) == {"has_more": True, "next_page": 3}
    assert parse_link_header(None) == {"has_more": False, "next_page": None}
    assert parse_link_header("garbage; not a link header") == {"has_more": False, "next_page": None}
