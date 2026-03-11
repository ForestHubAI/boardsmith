# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gerber File Validator.

Validates Gerber and drill output files produced by the PCB pipeline:
  - Required manufacturing layers present
  - Gerber format header recognised (RS-274X)
  - Drill file (Excellon format) present
  - Board outline layer present (Edge.Cuts)
  - File size sanity check (non-empty)

Usage::

    from boardsmith_hw.gerber_validator import GerberValidator
    v = GerberValidator()
    report = v.validate(gerber_dir)
    if report.valid:
        print("All layers OK")
    else:
        for issue in report.issues:
            print(f"  {issue}")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Expected layer suffixes (KiCad Gerber export naming conventions)
# ---------------------------------------------------------------------------

# Required for manufacturing
_REQUIRED_LAYERS: dict[str, str] = {
    "F_Cu":      "Front copper (component side)",
    "B_Cu":      "Back copper",
    "F_Mask":    "Front solder mask",
    "B_Mask":    "Back solder mask",
    "Edge_Cuts": "Board outline",
}

# Phase 23.7: Additional recommended layers (not blocking but warned)
_RECOMMENDED_LAYERS: dict[str, str] = {
    "F_SilkS":   "Front silkscreen (RefDes labels)",
    "B_SilkS":   "Back silkscreen",
    "F_Paste":   "Front paste (SMT stencil)",
}

# Required drill file patterns
_DRILL_PATTERNS = [
    re.compile(r".*\.(drl|DRL|exc|EXC|xln|XLN)$"),
    re.compile(r".*-drl\.(gbr|GBR)$"),
    re.compile(r".*PTH.*\.(drl|DRL)$"),
]

# Gerber RS-274X header patterns
_GERBER_HEADER_PATTERNS = [
    re.compile(r"^%FS"),       # Format statement
    re.compile(r"^%MO"),       # Mode (inch/mm)
    re.compile(r"^G04 "),      # Comment (common first line)
    re.compile(r"^%TF\."),     # Attribute
    re.compile(r"^G\d+\*"),    # G-code
]

# Minimum file sizes for real Gerbers (stub Gerbers are ~50 bytes)
_MIN_REAL_GERBER_BYTES = 200
_MIN_STUB_WARNING_BYTES = 50


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LayerInfo:
    """Information about a single Gerber layer."""

    name: str
    path: Path
    size_bytes: int
    is_stub: bool          # True if file looks like a placeholder
    has_valid_header: bool


@dataclass
class GerberReport:
    """Result of Gerber directory validation."""

    valid: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    layers: list[LayerInfo] = field(default_factory=list)
    has_drill: bool = False
    has_outline: bool = False
    stub_gerbers: bool = False  # True if all Gerbers appear to be stubs

    def summary(self) -> str:
        lines = [f"Gerber validation: {'PASS' if self.valid else 'FAIL'}"]
        if self.issues:
            for issue in self.issues:
                lines.append(f"  ✗ {issue}")
        if self.warnings:
            for warning in self.warnings:
                lines.append(f"  ⚠ {warning}")
        lines.append(f"  Layers found: {len(self.layers)}")
        lines.append(f"  Drill file:   {'yes' if self.has_drill else 'no'}")
        lines.append(f"  Board outline:{'yes' if self.has_outline else 'no'}")
        if self.stub_gerbers:
            lines.append("  NOTE: Stub Gerbers — install kicad-cli for real output")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class GerberValidator:
    """Validates a Gerber output directory.

    Usage::

        report = GerberValidator().validate(Path("output/gerbers"))
    """

    def validate(self, gerber_dir: Path) -> GerberReport:
        """Validate the contents of a Gerber directory.

        Args:
            gerber_dir: Path to directory containing .gbr and .drl files.

        Returns:
            GerberReport with validation results.
        """
        report = GerberReport(valid=True)

        if not gerber_dir.exists():
            report.valid = False
            report.issues.append(f"Gerber directory does not exist: {gerber_dir}")
            return report

        all_files = list(gerber_dir.iterdir())
        if not all_files:
            report.valid = False
            report.issues.append("Gerber directory is empty")
            return report

        gbr_files = [
            f for f in all_files
            if f.suffix.lower() in (".gbr", ".gtl", ".gbl", ".gto",
                                    ".gbo", ".gts", ".gbs", ".gko")
        ]
        drl_files = [f for f in all_files if _is_drill_file(f)]

        # ------------------------------------------------------------------
        # Drill file check
        # ------------------------------------------------------------------
        if drl_files:
            report.has_drill = True
        else:
            report.warnings.append(
                "No drill file (.drl) found — required for board manufacturing"
            )

        # ------------------------------------------------------------------
        # Layer analysis
        # ------------------------------------------------------------------
        found_layer_names: set[str] = set()

        for gbr in gbr_files:
            layer_name = _extract_layer_name(gbr)
            size = gbr.stat().st_size
            is_stub = size < _MIN_REAL_GERBER_BYTES
            has_header = _check_gerber_header(gbr)

            info = LayerInfo(
                name=layer_name or gbr.name,
                path=gbr,
                size_bytes=size,
                is_stub=is_stub,
                has_valid_header=has_header,
            )
            report.layers.append(info)

            if layer_name:
                found_layer_names.add(layer_name)

            if not has_header and not is_stub:
                report.warnings.append(
                    f"Layer '{gbr.name}' does not start with RS-274X header"
                )

        # Board outline check
        if "Edge_Cuts" in found_layer_names:
            report.has_outline = True
        else:
            report.warnings.append(
                "No Edge_Cuts layer found — board outline missing"
            )

        # ------------------------------------------------------------------
        # Required layer checks
        # ------------------------------------------------------------------
        for layer_name, description in _REQUIRED_LAYERS.items():
            if layer_name not in found_layer_names:
                if layer_name in ("F_Mask", "B_Mask"):
                    report.warnings.append(
                        f"Missing {layer_name} ({description}) — "
                        "required for SMT assembly"
                    )
                elif layer_name == "Edge_Cuts":
                    pass  # Already handled above
                else:
                    report.issues.append(
                        f"Missing required layer {layer_name} ({description})"
                    )
                    report.valid = False

        # ------------------------------------------------------------------
        # Phase 23.7: Recommended layer checks (silkscreen, paste)
        # ------------------------------------------------------------------
        for layer_name, description in _RECOMMENDED_LAYERS.items():
            if layer_name not in found_layer_names:
                report.warnings.append(
                    f"Missing recommended layer {layer_name} ({description})"
                )

        # ------------------------------------------------------------------
        # Phase 23.7: Drill file content validation
        # ------------------------------------------------------------------
        for drl in drl_files:
            try:
                content = drl.read_text(encoding="utf-8", errors="ignore")
                if drl.stat().st_size < 50:
                    report.warnings.append(
                        f"Drill file '{drl.name}' appears to be a stub "
                        f"({drl.stat().st_size} bytes)"
                    )
                elif "T1" not in content and "T01" not in content:
                    report.warnings.append(
                        f"Drill file '{drl.name}' has no tool definitions — "
                        "may be incomplete"
                    )
            except OSError:
                pass

        # ------------------------------------------------------------------
        # Stub detection
        # ------------------------------------------------------------------
        real_layers = [l for l in report.layers if not l.is_stub]
        if report.layers and not real_layers:
            report.stub_gerbers = True
            report.warnings.append(
                "All Gerber files appear to be stubs — "
                "install kicad-cli for manufacturing-ready output"
            )

        # ------------------------------------------------------------------
        # Minimum copper layers
        # ------------------------------------------------------------------
        copper_layers = [
            l for l in report.layers
            if "Cu" in l.name or l.name.endswith(".gtl") or l.name.endswith(".gbl")
        ]
        if not copper_layers:
            report.issues.append("No copper layers found")
            report.valid = False

        return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_layer_name(path: Path) -> Optional[str]:
    """Extract KiCad layer name from Gerber filename.

    KiCad naming: <board-name>-<LayerName>.gbr
    e.g. pcb-F_Cu.gbr → "F_Cu"
         pcb-B_Mask.gbr → "B_Mask"
    """
    stem = path.stem
    # Handle KiCad 6 naming: board-name-Layer_Name
    # Try splitting on last hyphen
    if "-" in stem:
        candidate = stem.rsplit("-", 1)[-1]
        # Validate it looks like a KiCad layer name (accept both F.Cu and F_Cu)
        normalized = candidate.replace(".", "_")
        if re.match(r"^[FB]_[A-Za-z_]+$|^Edge_Cuts$|^In\d+_Cu$", normalized):
            return normalized

    # Common Gerber extension suffixes (legacy naming)
    ext_map = {
        ".gtl": "F_Cu", ".gbl": "B_Cu",
        ".gto": "F_SilkS", ".gbo": "B_SilkS",
        ".gts": "F_Mask", ".gbs": "B_Mask",
        ".gko": "Edge_Cuts",
    }
    return ext_map.get(path.suffix.lower())


def _is_drill_file(path: Path) -> bool:
    """Return True if file looks like an Excellon drill file."""
    return any(pat.match(path.name) for pat in _DRILL_PATTERNS)


def _check_gerber_header(path: Path) -> bool:
    """Return True if the file starts with a recognisable RS-274X header."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for _ in range(5):
                line = fh.readline().strip()
                if any(pat.match(line) for pat in _GERBER_HEADER_PATTERNS):
                    return True
        return False
    except OSError:
        return False
