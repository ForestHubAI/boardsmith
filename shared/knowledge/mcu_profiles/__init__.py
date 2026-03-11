# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCU Device Profiles — one per MPN.

Layer 1 Hardware Knowledge: complete pin model, power domains, clocking,
boot/reset, debug, mandatory components, IO rules, peripheral patterns,
layout constraints, and firmware bindings.
"""
from __future__ import annotations

from shared.knowledge.mcu_profile_schema import MCUDeviceProfile

# Registry of all MCU profiles — populated by imports below
_PROFILES: dict[str, MCUDeviceProfile] = {}


def register(profile: MCUDeviceProfile) -> None:
    _PROFILES[profile.identity.mpn] = profile


def get(mpn: str) -> MCUDeviceProfile | None:
    return _PROFILES.get(mpn)


def get_all() -> dict[str, MCUDeviceProfile]:
    return dict(_PROFILES)


def get_by_family(family: str) -> list[MCUDeviceProfile]:
    return [p for p in _PROFILES.values() if p.identity.family == family]


# Auto-import profile modules to populate the registry
from . import esp32_s3_wroom1 as _esp32_s3  # noqa: E402, F401
from . import stm32g431 as _stm32g4        # noqa: E402, F401
from . import rp2040 as _rp2040            # noqa: E402, F401
