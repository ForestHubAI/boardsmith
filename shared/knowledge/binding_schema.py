# SPDX-License-Identifier: AGPL-3.0-or-later
"""Binding Layer schema — HW↔SW connection layer (Domain 14).

The thin, formal bridge between Hardware Knowledge (Layer 1) and
Software Knowledge (Layer 2).

Architecture:
    Logical Driver Contract      ← abstract, stable
            ↓
    Library Adapter Layer         ← per library, versioned
            ↓
    Concrete Implementation       ← generated code

Boardsmith NEVER hardcodes a concrete library API. It always goes through
a Binding Contract → Library Adapter → Code Template chain.

See DBroadmap.md for the full specification.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .software_profile_schema import IntegrationType


# ---------------------------------------------------------------------------
# Logical Driver Contract — abstract interface
# ---------------------------------------------------------------------------

class Parameter(BaseModel):
    name: str
    type: str                      # "float", "uint8_t", "int16_t"
    description: str = ""
    default: str | None = None


class FunctionSignature(BaseModel):
    name: str
    parameters: list[Parameter] = Field(default_factory=list)
    return_type: str = "int"       # Default: error code


class Capability(BaseModel):
    """A logical capability, e.g. 'temperature_read'."""
    name: str                      # "temperature_read"
    description: str = ""
    return_type: str = "float"
    parameters: list[Parameter] = Field(default_factory=list)
    required: bool = True          # Must every adapter implement this?


class LogicalDriverContract(BaseModel):
    """Abstract interface — independent of concrete library.

    Defines WHAT a driver must be able to do, not HOW.
    Example: A temperature sensor must support temperature_read().
    """
    contract_id: str               # "temperature_sensor_v1"
    contract_version: str = "1.0.0"
    category: str                  # "sensor" | "display" | "comms" | "storage" | "power"
    description: str = ""
    capabilities: list[Capability] = Field(default_factory=list)
    init_signature: FunctionSignature | None = None
    deinit_signature: FunctionSignature | None = None


# ---------------------------------------------------------------------------
# Library Adapter — maps contract to concrete library calls
# ---------------------------------------------------------------------------

class CodeTemplate(BaseModel):
    """Concrete code snippet for a capability."""
    template: str                  # "bme280_get_sensor_data(BME280_ALL, &data, &dev)"
    includes: list[str] = Field(default_factory=list)
    error_handling: str = "return_code"   # "check_rslt" | "return_code" | "exception"


class LibraryAdapter(BaseModel):
    """Mapping: Logical Contract → concrete library calls.

    One adapter per library. Swappable without changing the HW profile.
    """
    adapter_id: str                        # "bme280_bosch_adapter_v1"
    contract_id: str                       # "temperature_sensor_v1"
    driver_option_key: str                 # "bosch_official"
    target_sdk: str                        # "esp-idf" | "pico-sdk" | "stm32hal" | "zephyr"

    # Mapping: Logical Capability → concrete code
    capability_mappings: dict[str, CodeTemplate] = Field(default_factory=dict)

    # Integration: what goes into the project?
    required_includes: list[str] = Field(default_factory=list)
    required_defines: list[str] = Field(default_factory=list)
    required_compile_flags: list[str] = Field(default_factory=list)
    init_template: str = ""                # Code template for initialization
    deinit_template: str = ""


# ---------------------------------------------------------------------------
# Binding Record — the concrete glue for a project
# ---------------------------------------------------------------------------

class BindingRecord(BaseModel):
    """Concrete binding record — connects a component in a context with a driver.

    This is the actual 'glue' between HW and SW for a project.
    """
    component_mpn: str                     # "BME280"
    hardware_contract: str                 # "i2c_sensor_v1" (from MCU Profile)
    software_contract: str                 # "temperature_sensor_v1" (from SW Profile)
    selected_driver: str                   # "bosch_bme280_c_v3.5.1"
    selected_adapter: str                  # "bme280_bosch_adapter_v1"
    target: str                            # "esp32"
    sdk: str                               # "esp-idf"
    pinned_version: str = ""               # "v3.5.1" — no floating!
    integration_method: IntegrationType = IntegrationType.source_embed


# ---------------------------------------------------------------------------
# Contract Registry — lookup helpers
# ---------------------------------------------------------------------------

class ContractRegistry(BaseModel):
    """In-memory registry for resolving contracts → adapters → code."""
    contracts: dict[str, LogicalDriverContract] = Field(default_factory=dict)
    adapters: dict[str, LibraryAdapter] = Field(default_factory=dict)

    def register_contract(self, contract: LogicalDriverContract) -> None:
        self.contracts[contract.contract_id] = contract

    def register_adapter(self, adapter: LibraryAdapter) -> None:
        self.adapters[adapter.adapter_id] = adapter

    def resolve_adapter(
        self, contract_id: str, target_sdk: str
    ) -> LibraryAdapter | None:
        """Find the best adapter for a contract + target SDK."""
        for adapter in self.adapters.values():
            if adapter.contract_id == contract_id and adapter.target_sdk == target_sdk:
                return adapter
        return None

    def resolve_code(
        self, contract_id: str, capability_name: str, target_sdk: str
    ) -> CodeTemplate | None:
        """Resolve a capability to concrete code via adapter."""
        adapter = self.resolve_adapter(contract_id, target_sdk)
        if adapter and capability_name in adapter.capability_mappings:
            return adapter.capability_mappings[capability_name]
        return None
