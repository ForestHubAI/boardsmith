# SPDX-License-Identifier: AGPL-3.0-or-later
"""Logical Driver Contracts — Layer 3 Binding Layer.

Abstract interfaces defining WHAT a driver must do, not HOW.
"""
from __future__ import annotations

from shared.knowledge.binding_schema import ContractRegistry, LogicalDriverContract

_REGISTRY = ContractRegistry()


def get_registry() -> ContractRegistry:
    return _REGISTRY


def register_contract(contract: LogicalDriverContract) -> None:
    _REGISTRY.register_contract(contract)


def get_contract(contract_id: str) -> LogicalDriverContract | None:
    return _REGISTRY.contracts.get(contract_id)


# Auto-import contract definitions
from . import temperature_sensor_v1 as _ts  # noqa: E402, F401
from . import imu_sensor_v1 as _imu         # noqa: E402, F401
from . import co2_sensor_v1 as _co2         # noqa: E402, F401
from . import display_oled_v1 as _disp      # noqa: E402, F401
from . import flash_storage_v1 as _flash    # noqa: E402, F401
from . import lora_transceiver_v1 as _lora  # noqa: E402, F401
