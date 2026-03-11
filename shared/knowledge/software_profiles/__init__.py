# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device Software Profiles — Layer 2 Software Knowledge.

Per-component software knowledge: drivers, licenses, quality, ecosystem support.
"""
from __future__ import annotations

from shared.knowledge.software_profile_schema import DeviceSoftwareProfile

_PROFILES: dict[str, DeviceSoftwareProfile] = {}


def register(profile: DeviceSoftwareProfile) -> None:
    _PROFILES[profile.component_mpn] = profile


def get(mpn: str) -> DeviceSoftwareProfile | None:
    return _PROFILES.get(mpn)


def get_all() -> dict[str, DeviceSoftwareProfile]:
    return dict(_PROFILES)


# Auto-import profile modules
from . import bme280 as _bme280    # noqa: E402, F401
from . import ssd1306 as _ssd1306  # noqa: E402, F401
from . import mpu6050 as _mpu6050  # noqa: E402, F401
from . import scd41 as _scd41      # noqa: E402, F401
from . import sx1276 as _sx1276    # noqa: E402, F401
from . import w25q128 as _w25q128  # noqa: E402, F401
