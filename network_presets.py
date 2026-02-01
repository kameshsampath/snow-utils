#!/usr/bin/env python3
# Copyright 2026 Kamesh Sampath
# Generated with Cortex Code
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
"""
IPv4 preset providers and network rule enums for Snowflake.

Provides:
- NetworkRuleMode and NetworkRuleType enums
- Mode/type validation
- IPv4 preset fetchers (GitHub Actions, Google App Scripts, local IP)
- CIDR collection utility
"""

from enum import Enum
from functools import lru_cache

import requests


class NetworkRuleMode(str, Enum):
    """Snowflake network rule modes."""

    INGRESS = "INGRESS"
    INTERNAL_STAGE = "INTERNAL_STAGE"
    EGRESS = "EGRESS"
    POSTGRES_INGRESS = "POSTGRES_INGRESS"
    POSTGRES_EGRESS = "POSTGRES_EGRESS"


class NetworkRuleType(str, Enum):
    """Snowflake network rule value types."""

    IPV4 = "IPV4"
    HOST_PORT = "HOST_PORT"
    PRIVATE_HOST_PORT = "PRIVATE_HOST_PORT"
    AWSVPCEID = "AWSVPCEID"


VALID_MODE_TYPES: dict[NetworkRuleMode, list[NetworkRuleType]] = {
    NetworkRuleMode.INGRESS: [NetworkRuleType.IPV4, NetworkRuleType.AWSVPCEID],
    NetworkRuleMode.INTERNAL_STAGE: [NetworkRuleType.IPV4, NetworkRuleType.AWSVPCEID],
    NetworkRuleMode.EGRESS: [NetworkRuleType.IPV4, NetworkRuleType.HOST_PORT],
    NetworkRuleMode.POSTGRES_INGRESS: [NetworkRuleType.IPV4, NetworkRuleType.AWSVPCEID],
    NetworkRuleMode.POSTGRES_EGRESS: [NetworkRuleType.IPV4, NetworkRuleType.HOST_PORT],
}


def validate_mode_type(mode: NetworkRuleMode, rule_type: NetworkRuleType) -> bool:
    """Check if mode/type combination is valid per Snowflake docs."""
    return rule_type in VALID_MODE_TYPES.get(mode, [])


def get_valid_types_for_mode(mode: NetworkRuleMode) -> list[str]:
    """Get list of valid type names for a given mode."""
    return [t.value for t in VALID_MODE_TYPES.get(mode, [])]


@lru_cache(maxsize=1)
def get_github_actions_ips() -> tuple[str, ...]:
    """
    Fetch GitHub Actions runner IPv4 CIDRs from GitHub meta API.

    Returns a tuple for cacheability. The GitHub meta API provides
    IP ranges used by GitHub Actions runners.

    See: https://api.github.com/meta
    """
    response = requests.get("https://api.github.com/meta", timeout=30)
    response.raise_for_status()
    return tuple(response.json().get("actions", []))


@lru_cache(maxsize=1)
def get_google_ips() -> tuple[str, ...]:
    """
    Fetch Google IPv4 ranges from gstatic.com.

    Returns a tuple for cacheability. These are Google's published
    IP ranges used by various Google services.

    See: https://www.gstatic.com/ipranges/goog.json
    """
    response = requests.get("https://www.gstatic.com/ipranges/goog.json", timeout=30)
    response.raise_for_status()
    prefixes = response.json().get("prefixes", [])
    return tuple(p["ipv4Prefix"] for p in prefixes if "ipv4Prefix" in p)


def get_local_ip() -> str:
    """
    Get current public IP address with /32 CIDR suffix.

    Uses ipify.org API to detect the public IP of the current machine.
    """
    response = requests.get("https://api.ipify.org", timeout=10)
    response.raise_for_status()
    return f"{response.text.strip()}/32"


def collect_ipv4_cidrs(
    with_local: bool = True,
    with_gh: bool = False,
    with_google: bool = False,
    extra_cidrs: list[str] | None = None,
) -> list[str]:
    """
    Collect IPv4 CIDRs from enabled presets and extra values.

    Args:
        with_local: Include current public IP (default: True)
        with_gh: Include GitHub Actions runner IPs
        with_google: Include Google App Scripts IPs
        extra_cidrs: Additional CIDRs to include

    Returns:
        Deduplicated list of CIDRs preserving insertion order
    """
    cidrs: list[str] = []

    if with_local:
        cidrs.append(get_local_ip())

    if with_gh:
        cidrs.extend(get_github_actions_ips())

    if with_google:
        cidrs.extend(get_google_ips())

    if extra_cidrs:
        cidrs.extend(extra_cidrs)

    return list(dict.fromkeys(cidrs))
