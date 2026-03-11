# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end CLI smoke tests — invoke the real `boardsmith-fw` binary via subprocess.

These tests verify that all CLI commands exit with the expected codes and
produce correct output, catching integration regressions that pure Python
API tests would miss (argument parsing, click wiring, stdout format, etc.).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURE_DIR  = Path(__file__).parent.parent / "fixtures"
VIBE_FIXTURE = FIXTURE_DIR / "boardsmith_hw"
VALID_HIR    = VIBE_FIXTURE / "hir_valid_esp32_bme280.json"
INVALID_HIR  = VIBE_FIXTURE / "hir_invalid_i2c_addr_conflict.json"
GRAPH_JSON   = FIXTURE_DIR  / "hardware_graph_esp32_bme280.json"

# Resolve CLI: prefer installed binary, fall back to direct module invocation.
_BIN = shutil.which("boardsmith-fw")
CLI  = [_BIN] if _BIN else [sys.executable, "-m", "synth_core.cli"]


def _run(*args: str, timeout: int = 60, **kwargs) -> subprocess.CompletedProcess:
    """Run the CLI with the given sub-command arguments."""
    return subprocess.run(
        [*CLI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Shared synthesis fixture (class-scoped to run once per TestSynthesize class)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def synth_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run `boardsmith-fw synthesize` once and return the output directory."""
    out = tmp_path_factory.mktemp("synth_out")
    _run(
        "synthesize",
        "--prompt", "ESP32 with BME280 temperature sensor over I2C",
        "--out", str(out),
        "--no-llm",
        "--seed", "42",
        "--confidence-threshold", "0.30",
    )
    return out


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

class TestBasicInvocation:
    def test_help_exits_zero(self):
        r = _run("--help")
        assert r.returncode == 0

    def test_help_mentions_synthesize(self):
        r = _run("--help")
        assert "synthesize" in r.stdout

    def test_help_mentions_validate(self):
        r = _run("--help")
        assert "validate" in r.stdout

    def test_version_exits_zero(self):
        r = _run("--version")
        assert r.returncode == 0

    def test_version_contains_version_string(self):
        r = _run("--version")
        assert "version" in r.stdout.lower()

    def test_unknown_command_exits_nonzero(self):
        r = _run("nonexistent-command")
        assert r.returncode != 0


# ---------------------------------------------------------------------------
# validate-hir
# ---------------------------------------------------------------------------

class TestValidateHir:
    def test_valid_hir_exits_zero(self):
        r = _run("validate-hir", "--hir", str(VALID_HIR))
        assert r.returncode == 0

    def test_valid_hir_prints_valid(self):
        r = _run("validate-hir", "--hir", str(VALID_HIR))
        combined = r.stdout + r.stderr
        assert "VALID" in combined.upper()

    def test_invalid_hir_exits_one(self):
        r = _run("validate-hir", "--hir", str(INVALID_HIR))
        assert r.returncode == 1

    def test_invalid_hir_prints_invalid_or_error(self):
        r = _run("validate-hir", "--hir", str(INVALID_HIR))
        combined = r.stdout + r.stderr
        assert "INVALID" in combined.upper() or "error" in combined.lower()

    def test_validate_json_format_is_parseable(self):
        r = _run("validate-hir", "--hir", str(VALID_HIR), "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "valid" in data

    def test_validate_json_valid_true_for_valid_hir(self):
        r = _run("validate-hir", "--hir", str(VALID_HIR), "--format", "json")
        data = json.loads(r.stdout)
        assert data["valid"] is True

    def test_validate_json_has_summary_block(self):
        r = _run("validate-hir", "--hir", str(VALID_HIR), "--format", "json")
        data = json.loads(r.stdout)
        assert "summary" in data
        assert "errors" in data["summary"]

    def test_validate_diagnostics_file_written(self, tmp_path):
        diag = tmp_path / "diag.json"
        _run("validate-hir", "--hir", str(VALID_HIR), "--diagnostics", str(diag))
        assert diag.exists()
        data = json.loads(diag.read_text())
        assert "valid" in data

    def test_missing_hir_file_exits_nonzero(self):
        r = _run("validate-hir", "--hir", "/nonexistent/path.json")
        assert r.returncode != 0


# ---------------------------------------------------------------------------
# list-components
# ---------------------------------------------------------------------------

class TestListComponents:
    def test_list_exits_zero(self):
        r = _run("list-components")
        assert r.returncode == 0

    def test_list_json_format_exits_zero(self):
        r = _run("list-components", "--format", "json")
        assert r.returncode == 0

    def test_list_json_is_valid_json(self):
        r = _run("list-components", "--format", "json")
        data = json.loads(r.stdout)
        assert isinstance(data, list)

    def test_list_json_contains_esp32(self):
        r = _run("list-components", "--format", "json")
        mpns = {c["mpn"] for c in json.loads(r.stdout)}
        assert "ESP32-WROOM-32" in mpns

    def test_list_json_contains_bme280(self):
        r = _run("list-components", "--format", "json")
        mpns = {c["mpn"] for c in json.loads(r.stdout)}
        assert "BME280" in mpns

    def test_filter_by_category_mcu_returns_only_mcus(self):
        r = _run("list-components", "--format", "json", "--category", "mcu")
        data = json.loads(r.stdout)
        assert len(data) > 0
        assert all(c["category"] == "mcu" for c in data)

    def test_filter_by_category_sensor_returns_only_sensors(self):
        r = _run("list-components", "--format", "json", "--category", "sensor")
        data = json.loads(r.stdout)
        assert len(data) > 0
        assert all(c["category"] == "sensor" for c in data)

    def test_filter_by_interface_i2c(self):
        r = _run("list-components", "--format", "json", "--interface", "I2C")
        data = json.loads(r.stdout)
        assert len(data) > 0
        assert all("I2C" in c.get("interface_types", []) for c in data)

    def test_filter_by_max_cost(self):
        r = _run("list-components", "--format", "json", "--max-cost", "2.0")
        data = json.loads(r.stdout)
        costs = [c["unit_cost_usd"] for c in data if c.get("unit_cost_usd")]
        assert all(cost <= 2.0 for cost in costs)


# ---------------------------------------------------------------------------
# export-hir
# ---------------------------------------------------------------------------

class TestExportHir:
    def test_export_hir_exits_zero(self, tmp_path):
        out = tmp_path / "hir.json"
        r = _run("export-hir", "--graph", str(GRAPH_JSON), "--output", str(out))
        assert r.returncode == 0

    def test_export_hir_creates_file(self, tmp_path):
        out = tmp_path / "hir.json"
        _run("export-hir", "--graph", str(GRAPH_JSON), "--output", str(out))
        assert out.exists()

    def test_export_hir_valid_json_version(self, tmp_path):
        out = tmp_path / "hir.json"
        _run("export-hir", "--graph", str(GRAPH_JSON), "--output", str(out))
        data = json.loads(out.read_text())
        assert data["version"] == "1.1.0"

    def test_export_hir_track_a(self, tmp_path):
        out = tmp_path / "hir.json"
        _run("export-hir", "--graph", str(GRAPH_JSON), "--output", str(out))
        data = json.loads(out.read_text())
        assert data["metadata"]["track"] == "A"

    def test_export_hir_has_components(self, tmp_path):
        out = tmp_path / "hir.json"
        _run("export-hir", "--graph", str(GRAPH_JSON), "--output", str(out))
        data = json.loads(out.read_text())
        assert len(data["components"]) >= 2


# ---------------------------------------------------------------------------
# generate-from-hir
# ---------------------------------------------------------------------------

class TestGenerateFromHir:
    def test_generate_exits_zero(self, tmp_path):
        r = _run(
            "generate-from-hir",
            "--hir", str(VALID_HIR),
            "--target", "esp32",
            "--out", str(tmp_path / "fw"),
        )
        assert r.returncode == 0

    def test_generate_creates_main_cpp(self, tmp_path):
        fw = tmp_path / "fw"
        _run("generate-from-hir", "--hir", str(VALID_HIR), "--target", "esp32", "--out", str(fw))
        assert (fw / "main.cpp").exists()

    def test_generate_creates_cmake(self, tmp_path):
        fw = tmp_path / "fw"
        _run("generate-from-hir", "--hir", str(VALID_HIR), "--target", "esp32", "--out", str(fw))
        assert (fw / "CMakeLists.txt").exists()


# ---------------------------------------------------------------------------
# synthesize — shared fixture so pipeline runs only once
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("synth_out")
class TestSynthesize:
    """Full pipeline tests using the shared synth_out fixture."""

    def test_synthesize_creates_hir_json(self, synth_out):
        assert (synth_out / "hir.json").exists()

    def test_synthesize_creates_bom_json(self, synth_out):
        assert (synth_out / "bom.json").exists()

    def test_synthesize_creates_diagnostics_json(self, synth_out):
        assert (synth_out / "diagnostics.json").exists()

    def test_synthesize_creates_netlist_json(self, synth_out):
        assert (synth_out / "netlist.json").exists()

    def test_synthesize_creates_kicad_sch(self, synth_out):
        assert (synth_out / "schematic.kicad_sch").exists()

    def test_synthesize_creates_report_md(self, synth_out):
        assert (synth_out / "synthesis_report.md").exists()

    def test_synthesize_hir_version_1_1_0(self, synth_out):
        data = json.loads((synth_out / "hir.json").read_text())
        assert data["version"] == "1.1.0"

    def test_synthesize_hir_track_b(self, synth_out):
        data = json.loads((synth_out / "hir.json").read_text())
        assert data["metadata"]["track"] == "B"

    def test_synthesize_hir_has_components(self, synth_out):
        data = json.loads((synth_out / "hir.json").read_text())
        assert len(data["components"]) >= 2

    def test_synthesize_hir_has_bom(self, synth_out):
        data = json.loads((synth_out / "hir.json").read_text())
        assert len(data["bom"]) >= 2

    def test_synthesize_kicad_sch_starts_with_kicad_sch(self, synth_out):
        content = (synth_out / "schematic.kicad_sch").read_text()
        assert content.startswith("(kicad_sch")

    def test_synthesize_kicad_sch_contains_lib_symbols(self, synth_out):
        content = (synth_out / "schematic.kicad_sch").read_text()
        assert "lib_symbols" in content

    def test_synthesize_report_mentions_confidence(self, synth_out):
        content = (synth_out / "synthesis_report.md").read_text()
        assert "confidence" in content.lower() or "Confidence" in content


# ---------------------------------------------------------------------------
# CLI help for sub-commands
# ---------------------------------------------------------------------------

class TestSubCommandHelp:
    @pytest.mark.parametrize("cmd", [
        "validate-hir",
        "list-components",
        "export-hir",
        "generate-from-hir",
        "synthesize",
    ])
    def test_subcommand_help_exits_zero(self, cmd):
        r = _run(cmd, "--help")
        assert r.returncode == 0

    @pytest.mark.parametrize("cmd", [
        "validate-hir",
        "list-components",
        "export-hir",
        "generate-from-hir",
        "synthesize",
    ])
    def test_subcommand_help_has_usage(self, cmd):
        r = _run(cmd, "--help")
        assert "Usage:" in r.stdout or "usage:" in r.stdout.lower()


# ---------------------------------------------------------------------------
# DRC unconnected pad warning in _print_results
# ---------------------------------------------------------------------------

class TestDrcUnconnectedWarning:
    """Unit tests for _print_results DRC warning display (no subprocess needed)."""

    @staticmethod
    def _capture_print_results(drc_count: int) -> str:
        """Invoke _print_results with a mock SynthesisResult and capture Rich output."""
        import io
        import sys
        # Ensure boardsmith_cli is importable
        _repo = Path(__file__).parent.parent.parent
        for _pkg in (str(_repo / "synthesizer"), str(_repo / "shared"), str(_repo / "boardsmith_cli")):
            if _pkg not in sys.path:
                sys.path.insert(0, _pkg)

        # Also add repo root so boardsmith_cli package is importable
        _repo_root = str(_repo)
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)

        from rich.console import Console
        from boardsmith_hw.synthesizer import SynthesisResult
        import boardsmith_cli.main as cli_main

        result = SynthesisResult(
            success=True,
            confidence=0.85,
            artifacts=[],
            drc_unconnected_count=drc_count,
        )

        buf = io.StringIO()
        old_console = cli_main.console
        cli_main.console = Console(file=buf, highlight=False, markup=False)
        try:
            # Provide a tmp out_dir that exists (artifacts list is empty so no files checked)
            import tempfile, os
            with tempfile.TemporaryDirectory() as tmpdir:
                cli_main._print_results(result, Path(tmpdir), False)
        finally:
            cli_main.console = old_console

        return buf.getvalue()

    def test_drc_unconnected_warning_shown(self):
        """When drc_unconnected_count=5, warning with pad count is shown."""
        output = self._capture_print_results(5)
        assert "5 unconnected pad" in output

    def test_no_drc_warning_when_zero(self):
        """When drc_unconnected_count=0, no DRC pad warning is shown."""
        output = self._capture_print_results(0)
        assert "unconnected pad" not in output
