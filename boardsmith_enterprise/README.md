# Boardsmith Enterprise Edition

This directory is the namespace for **proprietary enterprise add-ons**. Enterprise modules are distributed separately under a [Commercial License](../legal/commercial_license_agreement_v1.md) and require a valid license key.

## Architecture Rules

1. **CE never imports EE** — Community Edition code (`shared/`, `synthesizer/`, `compiler/`, `boardsmith_cli/`) must never import from `boardsmith_enterprise/`
2. **EE extends CE via plugins** — Enterprise modules register as plugins via the `boardsmith.plugins` entry_points group
3. **License gating** — Enterprise features check `shared.licensing.is_available()` before executing

## Planned Enterprise Modules

| Module | Description |
|--------|-------------|
| `knowledge_packs/` | Extended component libraries (500+ components) |
| `compliance/` | IEC 61508, ISO 26262 constraint templates |
| `thermal/` | Thermal modeling and simulation |
| `power/` | Power budget modeling, multi-rail optimization |
| `pcb_advanced/` | Advanced routing rules, impedance matching |
| `manufacturing/` | Gerber export, pick-and-place, DFM rules |
| `audit/` | Audit logs, versioned design history |
| `reporting/` | Enterprise reporting and dashboards |

## Example Plugin Registration

```toml
# In the enterprise package's pyproject.toml:
[project.entry-points."boardsmith.plugins"]
compliance = "boardsmith_enterprise.compliance.plugin:CompliancePlugin"
thermal = "boardsmith_enterprise.thermal.plugin:ThermalPlugin"
```

## License

All code in this directory is proprietary. See [Commercial License](../legal/commercial_license_agreement_v1.md).
