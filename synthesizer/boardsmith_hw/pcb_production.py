# SPDX-License-Identifier: AGPL-3.0-or-later
"""PCB Production Bundle Export.

Creates a JLCPCB-ready production ZIP from PCB pipeline output:

  <project>-jlcpcb.zip
  ├── gerbers/
  │   ├── pcb-F_Cu.gbr
  │   ├── pcb-B_Cu.gbr
  │   ├── pcb-Edge_Cuts.gbr
  │   ├── pcb-F_Mask.gbr
  │   ├── pcb-B_Mask.gbr
  │   ├── pcb-F_SilkS.gbr
  │   ├── pcb-B_SilkS.gbr
  │   └── pcb.drl
  ├── bom.csv            ← JLCPCB SMT assembly BOM format
  ├── centroid.csv       ← Component Placement List (CPL)
  └── design_rules.txt   ← IPC-2221 design rule summary

Usage::

    from boardsmith_hw.pcb_production import PcbProductionExporter
    exporter = PcbProductionExporter()
    bundle = exporter.export(pcb_result, hir_dict, out_dir=Path("./output"))
    print(f"Production bundle: {bundle.zip_path}")
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from boardsmith_hw.gerber_validator import GerberReport, GerberValidator
from boardsmith_hw.jlcpcb_validator import JLCPCBReport, JLCPCBValidator
from boardsmith_hw.pcb_design_rules import PcbDesignRules, build_design_rules


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProductionBundle:
    """Result of the production export.

    Attributes:
        zip_path:        Path to the output ZIP file.
        bom_csv:         BOM CSV content string.
        centroid_csv:    Centroid/CPL CSV content string.
        gerber_report:   Gerber validation report.
        jlcpcb_report:   JLCPCB parts availability report.
        design_rules:    PCB design rules derived from HIR.
        warnings:        Non-fatal issues.
        errors:          Fatal issues (zip may be incomplete).
    """

    zip_path: Optional[Path]
    bom_csv: str = ""
    centroid_csv: str = ""
    gerber_report: Optional[GerberReport] = None
    jlcpcb_report: Optional[JLCPCBReport] = None
    design_rules: Optional[PcbDesignRules] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ready_for_order(self) -> bool:
        """True if the bundle looks ready for JLCPCB ordering."""
        if self.errors:
            return False
        if self.gerber_report and not self.gerber_report.valid:
            return False
        return self.zip_path is not None and self.zip_path.exists()

    def summary(self) -> str:
        lines = [
            f"Production Bundle: {'READY' if self.ready_for_order else 'NOT READY'}",
        ]
        if self.zip_path:
            size_kb = self.zip_path.stat().st_size // 1024 if self.zip_path.exists() else 0
            lines.append(f"  ZIP:     {self.zip_path}  ({size_kb} kB)")
        if self.gerber_report:
            layers = len(self.gerber_report.layers)
            drill = "✓" if self.gerber_report.has_drill else "✗"
            outline = "✓" if self.gerber_report.has_outline else "✗"
            lines.append(f"  Layers:  {layers}  Drill: {drill}  Outline: {outline}")
        if self.jlcpcb_report:
            r = self.jlcpcb_report
            lines.append(
                f"  BOM:     {r.basic_count} basic, "
                f"{r.extended_count} extended (+${r.estimated_setup_fee_usd:.0f}), "
                f"{r.not_found_count} not found"
            )
        if self.errors:
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Centroid (CPL) generation
# ---------------------------------------------------------------------------


def _extract_kicad_placements(pcb_path: Path) -> dict[str, tuple[float, float, float, str]]:
    """Parse actual component placements from a .kicad_pcb file.

    Returns {ref_designator: (x_mm, y_mm, rotation_deg, layer)} for every
    footprint found.  Falls back to an empty dict if the file cannot be parsed.

    KiCad S-expression format example::

        (footprint "RF_Module:ESP32-WROOM-32" (layer "F.Cu")
          (at 30.0 30.0)
          (property "Reference" "U1" ...)
          ...
        )
    """
    result: dict[str, tuple[float, float, float, str]] = {}
    try:
        text = pcb_path.read_text(encoding="utf-8")
    except OSError:
        return result

    # Match footprint blocks: (footprint "..." (layer "...") (at x y [rot]) ...)
    # We look for (property "Reference" "REF") inside each block.
    # Strategy: scan for (footprint ...) and extract the first (at ...) and
    # (property "Reference" "...") within the same block.

    fp_pattern = re.compile(
        r'\(footprint\s+"[^"]*"\s+\(layer\s+"([^"]+)"\)'  # layer
        r'.*?\(at\s+([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)',  # at x y [rot]
        re.DOTALL,
    )
    ref_pattern = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')

    # Split text into footprint chunks to avoid cross-block matches
    # Find all footprint start positions
    fp_starts = [m.start() for m in re.finditer(r'\(footprint\s+"', text)]
    for i, start in enumerate(fp_starts):
        end = fp_starts[i + 1] if i + 1 < len(fp_starts) else len(text)
        chunk = text[start:end]

        at_m = re.search(
            r'\(at\s+([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)',
            chunk,
        )
        ref_m = ref_pattern.search(chunk)
        layer_m = re.search(r'\(layer\s+"([^"]+)"\)', chunk)

        if at_m and ref_m:
            x = float(at_m.group(1))
            y = float(at_m.group(2))
            rot = float(at_m.group(3)) if at_m.group(3) else 0.0
            ref = ref_m.group(1)
            layer_str = layer_m.group(1) if layer_m else "F.Cu"
            layer = "Bottom" if "B.Cu" in layer_str else "Top"
            result[ref] = (x, y, rot, layer)

    return result


def _build_centroid_csv(
    hir: dict,
    footprints: dict[str, str],
    pcb_path: Path | None = None,
) -> str:
    """Generate a JLCPCB-compatible Component Placement List (centroid file).

    Format: Designator,Val,Package,Mid X,Mid Y,Rotation,Layer

    When *pcb_path* is provided, actual placement coordinates are extracted
    from the .kicad_pcb file instead of using estimated grid positions.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])

    components = hir.get("components", [])

    # Try to extract real placements from the PCB file
    real_placements: dict[str, tuple[float, float, float, str]] = {}
    if pcb_path and pcb_path.exists():
        real_placements = _extract_kicad_placements(pcb_path)

    # Fallback grid assignment (mirrors PcbLayoutEngine ordering)
    mcu_y = 30.0
    sensor_y = 30.0
    power_y = 15.0
    passive_y = 50.0

    for comp in components:
        comp_id = comp.get("id", "?")
        mpn = comp.get("mpn", comp_id)
        role = comp.get("role", "other").lower()
        fp = footprints.get(comp_id, "")
        pkg = _footprint_to_package(fp)

        if comp_id in real_placements:
            x, y, rot, layer = real_placements[comp_id]
        else:
            # Estimated grid fallback
            if role == "mcu":
                x, y, rot, layer = 30.0, mcu_y, 0.0, "Top"
                mcu_y += 20.0
            elif role == "power":
                x, y, rot, layer = 80.0, power_y, 0.0, "Top"
                power_y += 10.0
            elif role in ("sensor", "comms", "display"):
                x, y, rot, layer = 130.0, sensor_y, 0.0, "Top"
                sensor_y += 15.0
            else:
                x, y, rot, layer = 80.0, passive_y, 0.0, "Top"
                passive_y += 6.0

        writer.writerow([comp_id, mpn, pkg, f"{x:.2f}", f"{y:.2f}", f"{rot:.1f}", layer])

    return buf.getvalue()


def _footprint_to_package(kicad_footprint: str) -> str:
    """Extract a short package name from a KiCad footprint string."""
    if not kicad_footprint:
        return ""
    # "Library:FootprintName" → "FootprintName"
    name = kicad_footprint.split(":")[-1] if ":" in kicad_footprint else kicad_footprint
    # Drop dimensions (e.g. "SOT-23-5_3x1.6mm_P0.95mm" → "SOT-23-5")
    m = re.match(r"([A-Za-z0-9_\-]+?)(?:_\d|\s)", name)
    return m.group(1) if m else name[:20]


# ---------------------------------------------------------------------------
# Main exporter
# ---------------------------------------------------------------------------


class PcbProductionExporter:
    """Packages PCB pipeline output into a JLCPCB-ready ZIP.

    Usage::

        exporter = PcbProductionExporter()
        bundle = exporter.export(pcb_result, hir_dict, out_dir)
    """

    def export(
        self,
        pcb_result: Any,
        hir_dict: dict,
        out_dir: Path,
        project_name: str = "boardsmith",
    ) -> ProductionBundle:
        """Create the production ZIP bundle.

        Args:
            pcb_result:   PcbResult from PcbPipeline.run().
            hir_dict:     HIR as plain dict (same one passed to PcbPipeline).
            out_dir:      Output directory for the ZIP file.
            project_name: Name prefix for the ZIP file.

        Returns:
            ProductionBundle with paths and reports.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        bundle = ProductionBundle(zip_path=None)

        # ------------------------------------------------------------------
        # 1. Design rules analysis
        # ------------------------------------------------------------------
        try:
            bundle.design_rules = build_design_rules(hir_dict)
        except Exception as exc:
            bundle.warnings.append(f"Design rules analysis failed: {exc}")

        # ------------------------------------------------------------------
        # 2. JLCPCB BOM validation
        # ------------------------------------------------------------------
        try:
            jlcpcb_validator = JLCPCBValidator()
            bundle.jlcpcb_report = jlcpcb_validator.validate(hir_dict)
            bom_csv = bundle.jlcpcb_report.to_bom_csv()
            bundle.bom_csv = bom_csv
        except Exception as exc:
            bundle.warnings.append(f"JLCPCB BOM validation failed: {exc}")
            bom_csv = _fallback_bom_csv(hir_dict)
            bundle.bom_csv = bom_csv

        # ------------------------------------------------------------------
        # 3. Centroid / CPL generation
        # ------------------------------------------------------------------
        try:
            footprints = getattr(pcb_result, "footprints", {})
            # Use actual PCB placement coordinates when available
            pcb_file = getattr(pcb_result, "pcb_path", None)
            centroid_csv = _build_centroid_csv(
                hir_dict, footprints,
                pcb_path=Path(pcb_file) if pcb_file else None,
            )
            bundle.centroid_csv = centroid_csv
        except Exception as exc:
            bundle.warnings.append(f"Centroid generation failed: {exc}")
            centroid_csv = "Designator,Val,Package,Mid X,Mid Y,Rotation,Layer\n"
            bundle.centroid_csv = centroid_csv

        # ------------------------------------------------------------------
        # 4. Gerber validation
        # ------------------------------------------------------------------
        gerber_dir = getattr(pcb_result, "gerber_dir", None)
        if gerber_dir and Path(gerber_dir).exists():
            try:
                gv = GerberValidator()
                bundle.gerber_report = gv.validate(Path(gerber_dir))
                if not bundle.gerber_report.valid:
                    bundle.warnings.extend(bundle.gerber_report.issues)
            except Exception as exc:
                bundle.warnings.append(f"Gerber validation failed: {exc}")
        else:
            bundle.warnings.append("No Gerber directory — cannot include manufacturing files")

        # ------------------------------------------------------------------
        # 5. Build ZIP
        # ------------------------------------------------------------------
        zip_path = out_dir / f"{project_name}-jlcpcb.zip"
        try:
            bundle.zip_path = _build_zip(
                zip_path=zip_path,
                gerber_dir=Path(gerber_dir) if gerber_dir else None,
                bom_csv=bom_csv,
                centroid_csv=centroid_csv,
                design_rules_txt=bundle.design_rules.summary() if bundle.design_rules else "",
            )
        except Exception as exc:
            bundle.errors.append(f"ZIP creation failed: {exc}")

        return bundle


def _build_zip(
    zip_path: Path,
    gerber_dir: Optional[Path],
    bom_csv: str,
    centroid_csv: str,
    design_rules_txt: str,
) -> Path:
    """Create the production ZIP file."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Gerber files
        if gerber_dir and gerber_dir.exists():
            for gbr_file in gerber_dir.iterdir():
                if gbr_file.is_file():
                    zf.write(gbr_file, f"gerbers/{gbr_file.name}")

        # BOM
        zf.writestr("bom.csv", bom_csv)

        # Centroid / CPL
        zf.writestr("centroid.csv", centroid_csv)

        # Design rules summary
        if design_rules_txt:
            zf.writestr("design_rules.txt", design_rules_txt)

        # README
        zf.writestr("README.txt", _JLCPCB_README)

    return zip_path


def _fallback_bom_csv(hir: dict) -> str:
    """Minimal BOM CSV when JLCPCB validator fails."""
    lines = ["Comment,Designator,Footprint,LCSC Part #"]
    for comp in hir.get("components", []):
        mpn = comp.get("mpn", "")
        cid = comp.get("id", "")
        if mpn:
            lines.append(f'"{mpn}","{cid}","","" ')
    return "\n".join(lines) + "\n"


_JLCPCB_README = """\
JLCPCB Production Bundle — generated by boardsmith
=================================================

Files:
  gerbers/    Gerber manufacturing files + drill file
  bom.csv     Bill of Materials in JLCPCB format
              (Comment, Designator, Footprint, LCSC Part #)
  centroid.csv  Component placement list (CPL) for SMT assembly
              (Designator, Val, Package, Mid X, Mid Y, Rotation, Layer)
  design_rules.txt  IPC-2221 trace width & signal integrity notes

Ordering at JLCPCB:
  1. Upload the gerbers/ directory (or the whole ZIP) at jlcpcb.com
  2. For SMT assembly: upload bom.csv + centroid.csv in the assembly step
  3. Verify LCSC part numbers for extended components

Note: If Gerber files are stubs (small file size), install kicad-cli and
re-run 'boardsmith pcb-export' to get real manufacturing-ready Gerbers.
"""
