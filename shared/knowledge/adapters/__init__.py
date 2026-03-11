# SPDX-License-Identifier: AGPL-3.0-or-later
"""Library Adapters — map Logical Driver Contracts to concrete library calls.

Each adapter bridges a specific (contract, library, target_sdk) combination.
"""
from __future__ import annotations

from shared.knowledge.binding_schema import LibraryAdapter
from shared.knowledge.contracts import get_registry

_ADAPTERS: dict[str, LibraryAdapter] = {}


def register(adapter: LibraryAdapter) -> None:
    _ADAPTERS[adapter.adapter_id] = adapter
    get_registry().register_adapter(adapter)


def get(adapter_id: str) -> LibraryAdapter | None:
    return _ADAPTERS.get(adapter_id)


def get_all() -> dict[str, LibraryAdapter]:
    return dict(_ADAPTERS)


def find_for_contract(contract_id: str, target_sdk: str | None = None) -> list[LibraryAdapter]:
    return [
        a for a in _ADAPTERS.values()
        if a.contract_id == contract_id
        and (target_sdk is None or a.target_sdk == target_sdk)
    ]


# Auto-import adapter modules — ESP-IDF (original 6)
from . import bme280_bosch_espidf as _bme280_espidf      # noqa: E402, F401
from . import ssd1306_u8g2_espidf as _ssd1306_espidf     # noqa: E402, F401
from . import mpu6050_i2cdev_espidf as _mpu6050_espidf   # noqa: E402, F401
from . import scd41_sensirion_espidf as _scd41_espidf    # noqa: E402, F401
from . import sx1276_radiolib_espidf as _sx1276_espidf   # noqa: E402, F401
from . import w25q128_generic_espidf as _w25q128_espidf  # noqa: E402, F401

# DB-5 / Phase 24.1: STM32 HAL adapters (6)
from . import bme280_bosch_stm32hal as _bme280_stm32hal      # noqa: E402, F401
from . import ssd1306_u8g2_stm32hal as _ssd1306_stm32hal     # noqa: E402, F401
from . import mpu6050_i2cdev_stm32hal as _mpu6050_stm32hal   # noqa: E402, F401
from . import scd41_sensirion_stm32hal as _scd41_stm32hal    # noqa: E402, F401
from . import w25q128_generic_stm32hal as _w25q128_stm32hal  # noqa: E402, F401
from . import sx1276_radiolib_stm32hal as _sx1276_stm32hal   # noqa: E402, F401

# DB-5: Pico-SDK adapters (3 — highest-priority contracts)
from . import bme280_bosch_picosdk as _bme280_picosdk    # noqa: E402, F401
from . import ssd1306_u8g2_picosdk as _ssd1306_picosdk  # noqa: E402, F401
from . import mpu6050_i2cdev_picosdk as _mpu6050_picosdk  # noqa: E402, F401

# DB-6: Zephyr adapters (6 — all contracts for nRF52840 + Zephyr targets)
from . import bme280_bosch_zephyr as _bme280_zephyr        # noqa: E402, F401
from . import mpu6050_i2cdev_zephyr as _mpu6050_zephyr    # noqa: E402, F401
from . import ssd1306_u8g2_zephyr as _ssd1306_zephyr      # noqa: E402, F401
from . import scd41_sensirion_zephyr as _scd41_zephyr     # noqa: E402, F401
from . import w25q128_generic_zephyr as _w25q128_zephyr   # noqa: E402, F401
from . import sx1276_radiolib_zephyr as _sx1276_zephyr    # noqa: E402, F401
