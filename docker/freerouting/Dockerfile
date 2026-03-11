# Boardsmith — FreeRouting + kicad-cli Docker image
# Provides a self-contained PCB auto-routing environment.
#
# Build:
#   docker build -t boardsmith/freerouting:latest docker/freerouting/
#
# Usage (via boardsmith pcb or autorouter.py automatically):
#   docker run --rm -v $(pwd)/output:/work boardsmith/freerouting:latest \
#     kicad-cli pcb export dsn --output /work/board.dsn /work/pcb.kicad_pcb

FROM ubuntu:22.04

# --------------------------------------------------------------------------
# System dependencies
# --------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    # Java runtime for FreeRouting
    default-jre-headless \
    # wget/curl for downloads
    wget \
    ca-certificates \
    # KiCad (kicad-cli is part of kicad package)
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# kicad-cli (KiCad 7+ command-line interface)
# --------------------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository --yes ppa:kicad/kicad-7.0-releases \
    && apt-get update \
    && apt-get install -y kicad \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# FreeRouting (CLI edition)
# --------------------------------------------------------------------------
# Download FreeRouting CLI JAR from GitHub releases
ARG FREEROUTING_VERSION=1.8.0
RUN wget -q -O /usr/local/bin/freerouting.jar \
    "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar"

# Wrapper script so `freerouting` works as a command
RUN echo '#!/bin/sh\nexec java -jar /usr/local/bin/freerouting.jar "$@"' \
    > /usr/local/bin/freerouting \
    && chmod +x /usr/local/bin/freerouting

# --------------------------------------------------------------------------
# Sanity checks
# --------------------------------------------------------------------------
RUN java -jar /usr/local/bin/freerouting.jar --help 2>&1 | head -3 || true
RUN kicad-cli --version

# --------------------------------------------------------------------------
# Working directory
# --------------------------------------------------------------------------
WORKDIR /work

# Default: show help
CMD ["freerouting", "--help"]
