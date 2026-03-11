# Boardsmith FreeRouting Docker Image

Self-contained PCB auto-routing environment with FreeRouting + kicad-cli.

## Build

```bash
docker build -t boardsmith/freerouting:latest docker/freerouting/
```

## Usage

`boardsmith pcb` automatically uses this image when Docker is available and
the image is built. The autorouter priority order is:

1. **Native FreeRouting** (if `freerouting` is on PATH or JAR found)
2. **Docker FreeRouting** (this image — no local install required)
3. **kicad-cli DRC only** (routing skipped, DRC report generated)
4. **Stub** (always works, no external tools)

## Manual usage

```bash
# Export DSN from .kicad_pcb
docker run --rm -v $(pwd)/output:/work boardsmith/freerouting:latest \
  kicad-cli pcb export dsn --output /work/board.dsn /work/pcb.kicad_pcb

# Route with FreeRouting
docker run --rm -v $(pwd)/output:/work boardsmith/freerouting:latest \
  freerouting -de /work/board.dsn -do /work/board.ses -mp 1

# Import routing results back
docker run --rm -v $(pwd)/output:/work boardsmith/freerouting:latest \
  kicad-cli pcb import ses --input /work/board.ses /work/pcb.kicad_pcb

# Export Gerbers
docker run --rm -v $(pwd)/output:/work boardsmith/freerouting:latest \
  kicad-cli pcb export gerbers --output /work/gerbers /work/pcb.kicad_pcb
```

## What's included

- **Ubuntu 22.04** base
- **OpenJDK** (headless) — for FreeRouting JAR
- **FreeRouting CLI** (v1.8.0) — PCB auto-router
- **kicad-cli** (KiCad 7.x) — DSN/SES/Gerber export
