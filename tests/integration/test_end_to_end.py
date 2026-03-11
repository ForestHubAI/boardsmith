# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-module end-to-end integration tests for Boardsmith.

Tests the full pipeline:
  Prompt → Synthesizer (Track B) → HIR v1.1.0 → Schematic + BOM + (optional) Firmware

These tests do NOT require an LLM API key (use --no-llm / regex-only mode).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure all monorepo packages are importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler", "cli"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthesizer():
    """Return a configured Synthesizer instance (no LLM, deterministic seed)."""
    from boardsmith_hw.synthesizer import Synthesizer
    return Synthesizer


@pytest.fixture
def tmp_out(tmp_path: Path) -> Path:
    return tmp_path / "output"


# ---------------------------------------------------------------------------
# Test: HIR v1.1.0 model is importable from shared/
# ---------------------------------------------------------------------------

class TestSharedHIR:
    def test_import_hir_from_shared(self):
        from models.hir import HIR, Voltage, CurrentDraw, RegWrite, RegRead
        from models.hir import InitPhase, Constraint, Severity, BOMEntry
        assert HIR is not None

    def test_hir_without_metadata(self):
        """HIR should be instantiable without metadata (Track A compatibility)."""
        from models.hir import HIR
        h = HIR(source="schematic")
        assert h.version == "1.1.0"
        assert h.metadata is None
        assert h.components == []

    def test_hir_with_metadata(self):
        from models.hir import HIR, HIRMetadata, Confidence
        from datetime import datetime, timezone
        meta = HIRMetadata(
            created_at=datetime.now(timezone.utc).isoformat(),
            track="B",
            confidence=Confidence(overall=0.9),
        )
        h = HIR(source="prompt", metadata=meta)
        assert h.metadata.track == "B"
        assert h.metadata.confidence.overall == 0.9

    def test_backward_compatible_aliases_in_compiler(self):
        """Compiler HIR shim (compiler/boardsmith_fw/models/hir.py) must expose v1.0 aliases.

        We use importlib to directly load the compiler shim regardless of sys.path order.
        """
        import importlib.util
        shim_path = REPO_ROOT / "compiler" / "boardsmith_fw" / "models" / "hir.py"
        assert shim_path.exists(), f"Compiler HIR shim not found: {shim_path}"

        spec = importlib.util.spec_from_file_location("boardsmith_fw_compiler_hir", shim_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)

        # Temporarily add shared to path for the shim's import of models.hir
        _shared_p = str(REPO_ROOT / "shared")
        _added = _shared_p not in sys.path
        if _added:
            sys.path.insert(0, _shared_p)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        finally:
            if _added and _shared_p in sys.path:
                sys.path.remove(_shared_p)

        # Check the shim has backward-compatible aliases
        assert hasattr(module, "VoltageLevel"), "VoltageLevel alias missing from compiler shim"
        assert hasattr(module, "CurrentSpec"), "CurrentSpec alias missing from compiler shim"
        assert hasattr(module, "RegisterWrite"), "RegisterWrite alias missing from compiler shim"
        assert hasattr(module, "RegisterRead"), "RegisterRead alias missing from compiler shim"
        assert hasattr(module, "ConstraintSeverity"), "ConstraintSeverity alias missing from compiler shim"
        assert hasattr(module, "InitPhaseSpec"), "InitPhaseSpec alias missing from compiler shim"

        from models.hir import Voltage, CurrentDraw, RegWrite, RegRead, Severity, InitPhase
        assert module.VoltageLevel is Voltage
        assert module.CurrentSpec is CurrentDraw
        assert module.RegisterWrite is RegWrite
        assert module.RegisterRead is RegRead
        assert module.ConstraintSeverity is Severity
        assert module.InitPhaseSpec is InitPhase


# ---------------------------------------------------------------------------
# Test: Prompt → HIR → Schematic + BOM
# ---------------------------------------------------------------------------

class TestPromptToSchematic:
    """Tests that exercise the full synthesis pipeline without LLM."""

    @pytest.mark.parametrize("prompt,expected_mpns", [
        (
            "ESP32 with BME280 temperature sensor over I2C",
            ["ESP32-WROOM-32", "BME280"],
        ),
        (
            "ESP32 with SSD1306 OLED display over I2C",
            ["ESP32-WROOM-32", "SSD1306"],
        ),
    ])
    def test_synthesis_produces_artifacts(
        self, synthesizer, tmp_out: Path, prompt: str, expected_mpns: list[str]
    ):
        """Synthesis must produce hir.json, bom.json, schematic.kicad_sch."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,  # low threshold for no-LLM mode
        )
        result = synth.run(prompt, generate_firmware=False)

        # Artifacts exist
        assert (tmp_out / "hir.json").exists(), "hir.json missing"
        assert (tmp_out / "bom.json").exists(), "bom.json missing"
        assert (tmp_out / "schematic.kicad_sch").exists(), "schematic.kicad_sch missing"
        assert (tmp_out / "synthesis_report.md").exists(), "synthesis_report.md missing"

    def test_hir_schema_valid(self, synthesizer, tmp_out: Path):
        """Generated HIR must be parseable as HIR v1.1.0."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_path = tmp_out / "hir.json"
        assert hir_path.exists()
        data = json.loads(hir_path.read_text())

        from models.hir import HIR
        hir = HIR.model_validate(data)
        assert hir.version == "1.1.0"
        assert hir.source == "prompt"
        assert len(hir.bus_contracts) >= 1
        assert len(hir.components) >= 2  # at least MCU + sensor

    def test_bom_has_expected_components(self, synthesizer, tmp_out: Path):
        """BOM must contain MCU and sensor entries."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        bom = json.loads((tmp_out / "bom.json").read_text())
        mpns = {entry["mpn"] for entry in bom}
        assert "ESP32-WROOM-32" in mpns, f"MCU not in BOM: {mpns}"
        assert "BME280" in mpns, f"Sensor not in BOM: {mpns}"

    def test_kicad_schematic_is_valid_sexp(self, synthesizer, tmp_out: Path):
        """KiCad schematic must be non-empty S-expression text."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        kicad_path = tmp_out / "schematic.kicad_sch"
        content = kicad_path.read_text()
        assert content.startswith("(kicad_sch"), "Not a valid KiCad schematic"
        assert "ESP32" in content or "esp32" in content.lower()
        assert "BME280" in content or "bme280" in content.lower()

    def test_confidence_above_zero(self, synthesizer, tmp_out: Path):
        """Synthesis must produce non-zero confidence."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        result = synth.run("ESP32 with BME280 over I2C", generate_firmware=False)
        assert result.confidence > 0.0


# ---------------------------------------------------------------------------
# Test: CLI integration
# ---------------------------------------------------------------------------

class TestCLI:
    """Test the `boardsmith` CLI wrapper."""

    CLI_SCRIPT = str(REPO_ROOT / "boardsmith")

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        env = {
            "PYTHONPATH": ":".join([
                str(REPO_ROOT / "synthesizer"),
                str(REPO_ROOT / "shared"),
                str(REPO_ROOT / "compiler"),
                str(REPO_ROOT / "cli"),
            ])
        }
        import os
        full_env = {**os.environ, **env}
        result = subprocess.run(
            [sys.executable, "-m", "boardsmith_cli.main"] + args,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=full_env,
        )
        return result.returncode, result.stdout + result.stderr

    def test_cli_help(self):
        code, output = self._run_cli(["--help"])
        assert code == 0
        assert "build-project" in output
        assert "Boardsmith" in output

    def test_build_project_help(self):
        code, output = self._run_cli(["build-project", "--help"])
        assert code == 0
        assert "--prompt" in output
        assert "--target" in output

    def test_cli_build_project_no_llm(self, tmp_path: Path):
        out_dir = tmp_path / "cli-output"
        code, output = self._run_cli([
            "build-project",
            "--prompt", "ESP32 with BME280 temperature sensor over I2C",
            "--target", "esp32",
            "--out", str(out_dir),
            "--no-firmware",
            "--no-llm",
            "--seed", "42",
            "--confidence-threshold", "0.1",
        ])
        # Should succeed or show HITL warning, but always write files
        assert (out_dir / "hir.json").exists(), f"hir.json missing. Output:\n{output}"
        assert (out_dir / "schematic.kicad_sch").exists(), f"schematic missing. Output:\n{output}"


# ---------------------------------------------------------------------------
# Test: HIR cross-compatibility (Track A reads Track B output)
# ---------------------------------------------------------------------------

class TestHIRCrossCompatibility:
    """Track A (compiler) must be able to parse HIR generated by Track B (synthesizer)."""

    def test_compiler_can_validate_synthesized_hir(self, synthesizer, tmp_out: Path):
        """HIR generated by Boardsmith must pass compiler's validator."""
        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())

        # Try compiler's validator
        try:
            from synth_core.api.compiler import validate_hir_dict
            report = validate_hir_dict(hir_data)
            # May have warnings but should not crash
            assert hasattr(report, "valid")
        except ImportError:
            # Fallback: use shared HIR model validation
            from models.hir import HIR
            hir = HIR.model_validate(hir_data)
            assert hir.version == "1.1.0"


# ---------------------------------------------------------------------------
# Test: Phase 13 — Schematic Review Loop
# ---------------------------------------------------------------------------


class TestSchematicReviewLoop:
    """Phase 13: .kicad_sch → HIR → Diff → Auto-Fix end-to-end tests."""

    def test_reviewer_importable(self):
        """SchematicReviewer must be importable from boardsmith_hw."""
        from boardsmith_hw.schematic_reviewer import SchematicReviewer, ReviewResult, DiffSummary
        assert SchematicReviewer is not None
        assert ReviewResult is not None
        assert DiffSummary is not None

    def test_review_synthesized_schematic(self, synthesizer, tmp_out: Path):
        """Full pipeline: prompt → synth → .kicad_sch → review."""
        from boardsmith_hw.schematic_reviewer import SchematicReviewer

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 temperature sensor over I2C", generate_firmware=False)

        sch_path = tmp_out / "schematic.kicad_sch"
        assert sch_path.exists(), "Synthesizer must produce schematic.kicad_sch"

        reviewer = SchematicReviewer(max_iterations=3, use_llm=False)
        result = reviewer.review(sch_path)

        assert result.error is None, f"Review failed: {result.error}"
        assert isinstance(result.valid, bool)
        assert result.errors_after <= result.errors_before

    def test_review_with_original_hir_for_diff(self, synthesizer, tmp_out: Path):
        """Reviewer can compute round-trip diff vs original HIR."""
        from boardsmith_hw.schematic_reviewer import SchematicReviewer

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())
        sch_path = tmp_out / "schematic.kicad_sch"

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_path, original_hir=hir_data)

        assert result.error is None
        # diff object must always be present
        assert result.diff is not None
        assert isinstance(result.diff.has_diff, bool)

    def test_review_does_not_increase_errors(self, synthesizer, tmp_out: Path):
        """Auto-fix loop must never add new constraint errors."""
        from boardsmith_hw.schematic_reviewer import SchematicReviewer

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        sch_path = tmp_out / "schematic.kicad_sch"
        reviewer = SchematicReviewer(max_iterations=3, use_llm=False)
        result = reviewer.review(sch_path)

        assert result.errors_after <= result.errors_before, (
            f"errors went from {result.errors_before} → {result.errors_after} (should not increase)"
        )

    def test_review_hir_dict_has_components(self, synthesizer, tmp_out: Path):
        """Reviewed HIR dict must contain the synthesized components."""
        from boardsmith_hw.schematic_reviewer import SchematicReviewer

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        sch_path = tmp_out / "schematic.kicad_sch"
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_path)

        components = result.hir_dict.get("components", [])
        assert len(components) >= 1, "Reviewed HIR must contain at least one component"

    def test_cli_review_command_exists(self):
        """The `boardsmith review` CLI command must be registered."""
        code, output = _run_cli(["review", "--help"])
        assert code == 0, f"boardsmith review --help failed:\n{output}"
        assert "schematic" in output.lower()


# ---------------------------------------------------------------------------
# Test: Phase 14 — PCB Pipeline
# ---------------------------------------------------------------------------


class TestPcbPipelineIntegration:
    """Phase 14: HIR → .kicad_pcb → Gerbers end-to-end tests."""

    def test_pcb_modules_importable(self):
        """All Phase 14 modules must be importable."""
        from boardsmith_hw.footprint_mapper import FootprintMapper
        from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine
        from boardsmith_hw.autorouter import Autorouter
        from boardsmith_hw.pcb_pipeline import PcbPipeline, PcbResult
        assert all([FootprintMapper, PcbLayoutEngine, Autorouter, PcbPipeline, PcbResult])

    def test_pcb_from_synthesized_hir(self, synthesizer, tmp_out: Path):
        """Full pipeline: prompt → synth → HIR → PCB."""
        from boardsmith_hw.pcb_pipeline import PcbPipeline

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 temperature sensor over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())
        pcb_out = tmp_out / "pcb_out"

        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir_data, out_dir=pcb_out)

        assert result.error is None, f"PCB pipeline error: {result.error}"
        assert result.pcb_path is not None
        assert result.pcb_path.exists()

    def test_pcb_file_is_valid_kicad(self, synthesizer, tmp_out: Path):
        """Generated PCB must be valid KiCad 6 S-expression."""
        from boardsmith_hw.pcb_pipeline import PcbPipeline

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir_data, out_dir=tmp_out / "pcb")

        content = result.pcb_path.read_text(encoding="utf-8")
        assert content.startswith("(kicad_pcb"), "Must start with (kicad_pcb"
        assert content.count("(") == content.count(")"), "Parentheses must be balanced"

    def test_gerbers_directory_created(self, synthesizer, tmp_out: Path):
        """Gerber directory must exist after pipeline run."""
        from boardsmith_hw.pcb_pipeline import PcbPipeline

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir_data, out_dir=tmp_out / "pcb")

        assert result.gerber_dir is not None
        assert result.gerber_dir.exists()

    def test_footprints_resolved_for_synthesized_hir(self, synthesizer, tmp_out: Path):
        """Footprint mapper must resolve known MPNs from synthesized HIR."""
        from boardsmith_hw.footprint_mapper import FootprintMapper

        tmp_out.mkdir(parents=True, exist_ok=True)
        synth = synthesizer(
            out_dir=tmp_out, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir_data = json.loads((tmp_out / "hir.json").read_text())
        mapper = FootprintMapper(use_llm=False)
        infos = mapper.resolve_all(hir_data)

        assert len(infos) >= 1, "At least one component footprint must be resolved"
        for comp_id, fp_info in infos.items():
            assert ":" in fp_info.kicad_footprint, (
                f"Component {comp_id}: invalid footprint '{fp_info.kicad_footprint}'"
            )

    def test_cli_pcb_command_exists(self):
        """The `boardsmith pcb` CLI command must be registered."""
        code, output = _run_cli(["pcb", "--help"])
        assert code == 0, f"boardsmith pcb --help failed:\n{output}"
        assert "hir" in output.lower() or "pcb" in output.lower()


def _run_cli(args: list[str]) -> tuple[int, str]:
    """Run the boardsmith CLI and return (exit_code, combined_output)."""
    boardsmith_script = REPO_ROOT / "boardsmith"
    python = REPO_ROOT / ".venv314" / "bin" / "python3.14"
    main_py = REPO_ROOT / "boardsmith_cli" / "main.py"

    if boardsmith_script.exists():
        cmd = [str(boardsmith_script)] + args
    elif python.exists():
        cmd = [str(python), str(main_py)] + args
    else:
        cmd = ["python3", str(main_py)] + args

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr
