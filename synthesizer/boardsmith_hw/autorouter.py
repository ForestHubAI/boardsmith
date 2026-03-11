# SPDX-License-Identifier: AGPL-3.0-or-later
"""B14. Autorouter — PCB trace routing via external tools or stub.

Tries to route the PCB using available tools in priority order:
  1. FreeRouting (freerouting.jar or `freerouting` on PATH)
     .kicad_pcb → .dsn → freerouting → .ses → .kicad_pcb
  2. KiCad CLI (`kicad-cli pcb run-drc` for DRC check only)
  3. Stub — marks PCB as unrouted, records ratsnest-only status

Graceful degradation: all tools wrap in try/except.
`--no-llm` (stub) always works without any external installation.

DRC is run separately after routing if kicad-cli is available.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RoutingStats:
    """Statistics about the routing result.

    Attributes:
        trace_count:     Number of traces (segment S-expressions) in the PCB.
        via_count:       Number of vias placed.
        unrouted_count:  Number of unrouted connections (ratsnest lines).
        total_trace_len_mm: Approximate total trace length in mm.
    """

    trace_count: int = 0
    via_count: int = 0
    unrouted_count: int = 0
    total_trace_len_mm: float = 0.0

    def summary(self) -> str:
        parts = [f"{self.trace_count} traces"]
        if self.via_count:
            parts.append(f"{self.via_count} vias")
        if self.unrouted_count:
            parts.append(f"{self.unrouted_count} unrouted")
        if self.total_trace_len_mm > 0:
            parts.append(f"{self.total_trace_len_mm:.1f} mm total length")
        return ", ".join(parts)


@dataclass
class RouterResult:
    """Result of an autorouting attempt.

    Attributes:
        routed:     True if traces were actually generated.
        method:     How routing was done: "freerouting"|"kicad_cli_drc"|"stub".
        drc_errors: List of DRC error messages (empty if DRC not run or all pass).
        pcb_path:   Path to the (possibly updated) .kicad_pcb file.
        note:       Human-readable note about what happened.
        stats:      Routing statistics (trace/via counts, lengths).
    """

    routed: bool
    method: str            # "freerouting" | "kicad_cli_drc" | "stub"
    drc_errors: list[str] = field(default_factory=list)
    pcb_path: Path | None = None
    note: str = ""
    stats: RoutingStats = field(default_factory=RoutingStats)


# ---------------------------------------------------------------------------
# Autorouter
# ---------------------------------------------------------------------------


class Autorouter:
    """Attempts PCB trace routing using available external tools.

    Usage::

        router = Autorouter()
        result = router.route(pcb_path, hir_dict)
        if result.routed:
            print(f"Routed via {result.method}")
        else:
            print(f"Unrouted stub — install FreeRouting to auto-route")
    """

    # Minimum freerouting jar size to consider it valid
    _MIN_JAR_SIZE_BYTES = 100_000

    # Docker image name for FreeRouting (built from docker/freerouting/Dockerfile)
    _DOCKER_IMAGE = "boardsmith/freerouting:latest"

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        pcb_path: Path,
        hir_dict: dict[str, Any] | None = None,
    ) -> RouterResult:
        """Attempt to route *pcb_path*.

        Tries FreeRouting, then KiCad CLI DRC, then falls back to stub.

        Args:
            pcb_path:  Path to the .kicad_pcb file (modified in-place if routed).
            hir_dict:  Optional HIR dict for context (used for DRC net hints).

        Returns:
            RouterResult with routing outcome details.
        """
        pcb_path = Path(pcb_path)

        # 1. Try FreeRouting (native install)
        if self._freerouting_available():
            try:
                ok = self._run_freerouting(pcb_path)
                if ok:
                    stats = self._collect_routing_stats(pcb_path)
                    drc = self._run_drc(pcb_path)
                    return RouterResult(
                        routed=True,
                        method="freerouting",
                        drc_errors=drc,
                        pcb_path=pcb_path,
                        stats=stats,
                        note="Routed with FreeRouting" + (
                            f" — {len(drc)} DRC error(s)" if drc else " — DRC passed"
                        ) + f" ({stats.summary()})",
                    )
            except Exception as exc:
                log.warning("FreeRouting failed: %s", exc)

        # 2. Try Docker-based FreeRouting (no local install required)
        if self._docker_available():
            try:
                ok = self._run_freerouting_docker(pcb_path)
                if ok:
                    stats = self._collect_routing_stats(pcb_path)
                    drc = self._run_drc(pcb_path)
                    return RouterResult(
                        routed=True,
                        method="freerouting_docker",
                        drc_errors=drc,
                        pcb_path=pcb_path,
                        stats=stats,
                        note="Routed via Docker FreeRouting image" + (
                            f" — {len(drc)} DRC error(s)" if drc else " — DRC passed"
                        ) + f" ({stats.summary()})",
                    )
            except Exception as exc:
                log.warning("Docker FreeRouting failed: %s", exc)

        # 3. KiCad CLI — DRC only (no routing, but validates the unrouted PCB)
        if self._kicad_cli_available():
            drc = self._run_drc(pcb_path)
            stats = self._collect_routing_stats(pcb_path)
            return RouterResult(
                routed=False,
                method="kicad_cli_drc",
                drc_errors=drc,
                pcb_path=pcb_path,
                stats=stats,
                note="DRC run via kicad-cli (PCB is unrouted — install FreeRouting to auto-route)",
            )

        # 4. Stub — no tools available
        stats = self._collect_routing_stats(pcb_path)
        return RouterResult(
            routed=False,
            method="stub",
            drc_errors=[],
            pcb_path=pcb_path,
            stats=stats,
            note=(
                "PCB is unrouted. "
                "Install FreeRouting (https://freerouting.org) or KiCad CLI to enable auto-routing."
            ),
        )

    def drc_only(self, pcb_path: Path) -> list[str]:
        """Run DRC on *pcb_path* and return a list of error messages.

        Returns an empty list if DRC passes or kicad-cli is not available.
        """
        from boardsmith_hw.kicad_drc import KiCadChecker
        checker = KiCadChecker()
        result = checker.run_drc(Path(pcb_path))
        return result.error_messages

    # ------------------------------------------------------------------
    # Tool availability checks
    # ------------------------------------------------------------------

    @staticmethod
    def kicad_cli_available() -> bool:
        """True if `kicad-cli` is on the PATH."""
        return Autorouter._kicad_cli_available()

    @staticmethod
    def freerouting_available() -> bool:
        """True if FreeRouting is on the PATH or a known JAR path."""
        return Autorouter._freerouting_available()

    @classmethod
    def _kicad_cli_available(cls) -> bool:
        if shutil.which("kicad-cli") is not None:
            return True
        # macOS: KiCad.app bundle paths
        for p in [
            "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
            str(Path.home() / "Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
        ]:
            if Path(p).is_file():
                return True
        return False

    @classmethod
    def _kicad_cli_path(cls) -> str:
        """Return the kicad-cli executable path (including macOS bundle)."""
        found = shutil.which("kicad-cli")
        if found:
            return found
        for p in [
            "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
            str(Path.home() / "Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
        ]:
            if Path(p).is_file():
                return p
        return "kicad-cli"  # fallback

    @classmethod
    def _freerouting_available(cls) -> bool:
        # Check PATH
        if shutil.which("freerouting"):
            return True
        # Common JAR locations
        jar_paths = [
            Path.home() / ".local/bin/freerouting.jar",
            Path("/usr/local/bin/freerouting.jar"),
            Path("/opt/freerouting/freerouting.jar"),
        ]
        for p in jar_paths:
            if p.exists() and p.stat().st_size >= cls._MIN_JAR_SIZE_BYTES:
                return True
        return False

    @classmethod
    def _docker_available(cls) -> bool:
        """True if Docker is on PATH and the FreeRouting image is available."""
        if not shutil.which("docker"):
            return False
        try:
            r = subprocess.run(
                ["docker", "image", "inspect", cls._DOCKER_IMAGE],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Routing validation & statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_routing_stats(pcb_path: Path) -> RoutingStats:
        """Parse the .kicad_pcb to count traces, vias, and unrouted nets.

        Scans the S-expression text for ``(segment ...)``, ``(via ...)``,
        and unrouted ``(no_connect ...)`` entries.  Computes approximate
        total trace length from segment start/end coordinates.
        """
        import math as _math

        stats = RoutingStats()
        if not pcb_path.exists():
            return stats

        try:
            text = pcb_path.read_text(encoding="utf-8")
        except OSError:
            return stats

        # Count segments (routed traces)
        seg_pattern = re.compile(
            r'\(segment\s+\(start\s+([\d.]+)\s+([\d.]+)\)\s+'
            r'\(end\s+([\d.]+)\s+([\d.]+)\)'
        )
        total_len = 0.0
        for m in seg_pattern.finditer(text):
            stats.trace_count += 1
            x1, y1 = float(m.group(1)), float(m.group(2))
            x2, y2 = float(m.group(3)), float(m.group(4))
            total_len += _math.hypot(x2 - x1, y2 - y1)
        stats.total_trace_len_mm = round(total_len, 1)

        # Count vias
        stats.via_count = text.count("(via ")

        # Count unrouted connections (ratsnest)
        stats.unrouted_count = text.count("(no_connect")

        return stats

    def validate_routing(self, pcb_path: Path) -> list[str]:
        """Validate that routing produced usable traces.

        Returns a list of warnings/errors.  Empty list = routing OK.
        """
        issues: list[str] = []
        stats = self._collect_routing_stats(pcb_path)

        if stats.trace_count == 0:
            issues.append("No traces found — PCB is completely unrouted")
        if stats.unrouted_count > 0:
            issues.append(
                f"{stats.unrouted_count} unrouted connection(s) remain"
            )
        if stats.trace_count > 0 and stats.total_trace_len_mm < 1.0:
            issues.append(
                "Total trace length < 1 mm — routing may be incomplete"
            )

        return issues

    # ------------------------------------------------------------------
    # FreeRouting integration
    # ------------------------------------------------------------------

    def _run_freerouting(self, pcb_path: Path) -> bool:
        """Export .dsn, run FreeRouting, import .ses back into .kicad_pcb.

        Requires kicad-cli for .dsn export and .ses import.
        Returns True if routing succeeded and the PCB was updated.
        """
        if not self._kicad_cli_available():
            log.debug("FreeRouting: kicad-cli not available for .dsn export")
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dsn_path = tmp / "board.dsn"
            ses_path = tmp / "board.ses"

            # Export DSN
            kicad = self._kicad_cli_path()
            export_cmd = [
                kicad, "pcb", "export", "dsn",
                "--output", str(dsn_path),
                str(pcb_path),
            ]
            log.debug("FreeRouting DSN export: %s", " ".join(export_cmd))
            r = subprocess.run(export_cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not dsn_path.exists():
                log.warning("DSN export failed: %s", r.stderr)
                return False

            # Run FreeRouting
            fr_cmd = self._freerouting_command(dsn_path, ses_path)
            log.debug("FreeRouting route: %s", " ".join(str(c) for c in fr_cmd))
            r2 = subprocess.run(fr_cmd, capture_output=True, text=True, timeout=300)
            if r2.returncode != 0 or not ses_path.exists():
                log.warning("FreeRouting failed: %s", r2.stderr[:500])
                return False

            # Import SES back
            import_cmd = [
                kicad, "pcb", "import", "ses",
                "--input", str(ses_path),
                str(pcb_path),
            ]
            log.debug("FreeRouting SES import: %s", " ".join(import_cmd))
            r3 = subprocess.run(import_cmd, capture_output=True, text=True, timeout=60)
            if r3.returncode != 0:
                log.warning("SES import failed: %s", r3.stderr[:500])
                return False

        return True

    def _run_freerouting_docker(self, pcb_path: Path) -> bool:
        """Route the PCB using FreeRouting inside a Docker container.

        Mounts the PCB directory into the container, exports DSN via
        kicad-cli (inside the container), routes, then imports SES back.

        The Docker image ``boardsmith/freerouting:latest`` must be built from
        ``docker/freerouting/Dockerfile`` (bundled FreeRouting + kicad-cli).

        Returns True if routing succeeded.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dsn_path = tmp / "board.dsn"
            ses_path = tmp / "board.ses"

            pcb_dir = pcb_path.parent.resolve()
            pcb_name = pcb_path.name

            # Export DSN using kicad-cli inside Docker
            export_cmd = [
                "docker", "run", "--rm",
                "-v", f"{pcb_dir}:/work",
                "-v", f"{tmp}:/tmp/routing",
                self._DOCKER_IMAGE,
                "kicad-cli", "pcb", "export", "dsn",
                "--output", "/tmp/routing/board.dsn",
                f"/work/{pcb_name}",
            ]
            r = subprocess.run(export_cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not dsn_path.exists():
                log.warning("Docker DSN export failed: %s", r.stderr[:300])
                return False

            # Run FreeRouting inside Docker
            route_cmd = [
                "docker", "run", "--rm",
                "-v", f"{tmp}:/tmp/routing",
                self._DOCKER_IMAGE,
                "freerouting",
                "-de", "/tmp/routing/board.dsn",
                "-do", "/tmp/routing/board.ses",
                "-mp", "1",
            ]
            r2 = subprocess.run(route_cmd, capture_output=True, text=True, timeout=300)
            if r2.returncode != 0 or not ses_path.exists():
                log.warning("Docker FreeRouting failed: %s", r2.stderr[:300])
                return False

            # Import SES using kicad-cli inside Docker
            import_cmd = [
                "docker", "run", "--rm",
                "-v", f"{pcb_dir}:/work",
                "-v", f"{tmp}:/tmp/routing",
                self._DOCKER_IMAGE,
                "kicad-cli", "pcb", "import", "ses",
                "--input", "/tmp/routing/board.ses",
                f"/work/{pcb_name}",
            ]
            r3 = subprocess.run(import_cmd, capture_output=True, text=True, timeout=60)
            if r3.returncode != 0:
                log.warning("Docker SES import failed: %s", r3.stderr[:300])
                return False

        return True

    @classmethod
    def _freerouting_command(cls, dsn_path: Path, ses_path: Path) -> list:
        """Build the FreeRouting command line."""
        if shutil.which("freerouting"):
            return ["freerouting", "-de", str(dsn_path), "-do", str(ses_path),
                    "-mp", "1"]  # 1 routing pass

        # JAR mode
        jar_paths = [
            Path.home() / ".local/bin/freerouting.jar",
            Path("/usr/local/bin/freerouting.jar"),
            Path("/opt/freerouting/freerouting.jar"),
        ]
        for jar in jar_paths:
            if jar.exists():
                return ["java", "-jar", str(jar),
                        "-de", str(dsn_path), "-do", str(ses_path), "-mp", "1"]
        raise FileNotFoundError("FreeRouting JAR not found")

    # ------------------------------------------------------------------
    # DRC via kicad-cli (delegated to KiCadChecker)
    # ------------------------------------------------------------------

    def _run_drc(self, pcb_path: Path) -> list[str]:
        """Run DRC and return list of error messages.

        Delegates to KiCadChecker for the actual kicad-cli invocation.
        """
        from boardsmith_hw.kicad_drc import KiCadChecker
        checker = KiCadChecker()
        result = checker.run_drc(pcb_path)
        return result.error_messages

    # ------------------------------------------------------------------
    # Gerber export
    # ------------------------------------------------------------------

    def export_gerbers(
        self,
        pcb_path: Path,
        gerber_dir: Path,
    ) -> bool:
        """Export Gerber files from the PCB.

        Uses `kicad-cli pcb export gerbers` if available.
        Falls back to writing stub .gbr files so the pipeline always
        produces the expected output directory.

        Returns:
            True if kicad-cli was used (real Gerbers), False if stub.
        """
        gerber_dir.mkdir(parents=True, exist_ok=True)

        if self._kicad_cli_available():
            try:
                kicad = self._kicad_cli_path()
                cmd = [
                    kicad, "pcb", "export", "gerbers",
                    "--output", str(gerber_dir),
                    str(pcb_path),
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    log.info("Gerbers exported to %s", gerber_dir)
                    return True
                log.warning("kicad-cli gerber export failed: %s", r.stderr[:200])
            except Exception as exc:
                log.warning("Gerber export failed: %s", exc)

        # Stub: write placeholder .gbr files
        _write_stub_gerbers(gerber_dir, pcb_path.stem)
        return False


# ---------------------------------------------------------------------------
# Stub Gerber writer
# ---------------------------------------------------------------------------

def _write_stub_gerbers(gerber_dir: Path, stem: str) -> None:
    """Write stub Gerber files (clearly marked as placeholders)."""
    stub_layers = {
        f"{stem}-F_Cu.gbr":       "Front copper (placeholder — install kicad-cli for real Gerbers)",
        f"{stem}-B_Cu.gbr":       "Back copper (placeholder)",
        f"{stem}-F_SilkS.gbr":    "Front silkscreen (placeholder)",
        f"{stem}-B_SilkS.gbr":    "Back silkscreen (placeholder)",
        f"{stem}-F_Mask.gbr":     "Front solder mask (placeholder)",
        f"{stem}-B_Mask.gbr":     "Back solder mask (placeholder)",
        f"{stem}-Edge_Cuts.gbr":  "Board outline (placeholder)",
        f"{stem}.drl":             "Drill file (placeholder)",
    }
    for fname, note in stub_layers.items():
        (gerber_dir / fname).write_text(
            f"%FSLAX46Y46*%\n%MOMM*%\n; {note}\nM02*\n",
            encoding="utf-8",
        )
    log.info("Stub Gerbers written to %s (install kicad-cli for real exports)", gerber_dir)
