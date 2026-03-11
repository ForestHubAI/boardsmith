# SPDX-License-Identifier: AGPL-3.0-or-later
"""Datasheet research pipeline: search → download → cache → extract.

Uses httpx for HTTP, pdfplumber for PDF text extraction.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_datasheet(mpn: str, manufacturer: str = "") -> str | None:
    """Try to find a datasheet PDF URL for the given MPN.

    Strategy: attempt known URL patterns (Espressif, TI, Bosch, etc.).
    Returns the first URL that responds with a PDF content-type.
    """
    mpn_l = mpn.lower()
    mpn_u = mpn.upper()

    patterns = [
        # Espressif
        f"https://www.espressif.com/sites/default/files/documentation/{mpn_l}_datasheet_en.pdf",
        # Bosch Sensortec
        f"https://www.bosch-sensortec.com/media/boschsensortec/downloads/{mpn_l}/{mpn_l}.pdf",
        # Texas Instruments
        f"https://www.ti.com/lit/ds/symlink/{mpn_l}.pdf",
        # STMicroelectronics
        f"https://www.st.com/resource/en/datasheet/{mpn_l}.pdf",
        # NXP
        f"https://www.nxp.com/docs/en/data-sheet/{mpn_u}.pdf",
        # Microchip / Atmel
        f"https://ww1.microchip.com/downloads/en/DeviceDoc/{mpn_u}.pdf",
        f"https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/{mpn_u}-datasheet.pdf",
        # Analog Devices / Maxim
        f"https://www.analog.com/media/en/technical-documentation/data-sheets/{mpn_u}.pdf",
        # ON Semiconductor / onsemi
        f"https://www.onsemi.com/pdf/datasheet/{mpn_l}-d.pdf",
        # Infineon
        f"https://www.infineon.com/dgdl/{mpn_u}_DataSheet.pdf",
    ]

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for url in patterns:
            try:
                resp = await client.head(url)
                ct = resp.headers.get("content-type", "")
                if resp.is_success and "pdf" in ct.lower():
                    return url
            except httpx.HTTPError:
                continue

    return None


# ---------------------------------------------------------------------------
# Download + Cache
# ---------------------------------------------------------------------------

async def download_datasheet(url: str, cache_dir: Path, mpn: str) -> Path | None:
    """Download a PDF and cache it locally. Returns local path or None."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    safe_mpn = re.sub(r"[^a-zA-Z0-9_-]", "_", mpn)[:64]
    filename = f"{safe_mpn}_{url_hash}.pdf"
    filepath = cache_dir / filename

    if filepath.exists():
        return filepath

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            if not resp.is_success:
                return None

            data = resp.content
            filepath.write_bytes(data)

            meta = {
                "url": url,
                "mpn": mpn,
                "downloaded_at": __import__("datetime").datetime.now().isoformat(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            filepath.with_suffix(".pdf.meta.json").write_text(json.dumps(meta, indent=2))

            return filepath
    except httpx.HTTPError:
        return None


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_from_datasheet(pdf_path: Path, mpn: str) -> Optional[dict]:
    """Extract structured info from a cached datasheet PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        # pdfplumber is an LLM extra — install with: pip install boardsmith[llm]
        return None

    try:
        text = ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:30]:  # limit to first 30 pages
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception:
        return None

    if len(text) < 100:
        return None

    result: dict = {"extracted_sections": {}}
    result["description"] = _extract_description(text, mpn)
    result["interface"] = _detect_interface(text)

    if result["interface"] == "I2C":
        result["i2c_address"] = _extract_i2c_address(text)

    result["pins"] = _extract_pins(text)
    result["registers"] = _extract_registers(text)
    result["timing_constraints"] = _extract_timing(text)

    result["extracted_sections"] = {
        "pinout": _extract_section(text, ["pin description", "pin configuration", "pinout", "pin assignment"]),
        "register_map": _extract_section(text, ["register map", "register description", "register table"]),
        "timing": _extract_section(text, ["timing", "ac characteristics", "dc characteristics"]),
        "init_sequence": _extract_section(text, ["initialization", "startup", "power-on", "configuration"]),
    }

    return result


def _extract_description(text: str, mpn: str) -> str:
    keywords = ["sensor", "controller", "converter", "driver", "transceiver", mpn.lower()]
    for line in text.split("\n")[:30]:
        stripped = line.strip()
        if len(stripped) < 20:
            continue
        lower = stripped.lower()
        if any(kw in lower for kw in keywords):
            return stripped[:200]
    # fallback: first non-trivial line
    for line in text.split("\n"):
        if len(line.strip()) > 20:
            return line.strip()[:200]
    return ""


def _detect_interface(text: str) -> str:
    lower = text.lower()
    counts = {
        "I2C": len(re.findall(r"\bi2c\b", lower)),
        "SPI": len(re.findall(r"\bspi\b", lower)),
        "UART": len(re.findall(r"\buart\b", lower)),
        "ADC": len(re.findall(r"\badc\b", lower)),
    }
    best = max(counts.items(), key=lambda x: x[1])
    return best[0] if best[1] > 3 else "OTHER"


def _extract_i2c_address(text: str) -> str | None:
    m = re.search(
        r"(?:slave\s+address|i2c\s+address|device\s+address)[^0-9x]*?(0x[0-9a-fA-F]{2})",
        text, re.IGNORECASE,
    )
    return m.group(1) if m else None


def _extract_pins(text: str) -> list[dict]:
    pins: list[dict] = []
    for m in re.finditer(
        r"(\d{1,3})\s+([\w]+)\s+(input|output|i/o|power|ground|analog|digital)",
        text, re.IGNORECASE,
    ):
        pins.append({
            "number": m.group(1),
            "name": m.group(2),
            "function": m.group(2),
            "electrical_type": m.group(3).lower(),
        })
        if len(pins) >= 50:
            break
    return pins


def _extract_registers(text: str) -> list[dict]:
    regs: list[dict] = []
    for m in re.finditer(
        r"(?:register|addr|address)\s*[=:]*\s*(0x[0-9a-fA-F]{1,4})\s*[-–:]\s*(\w[\w\s]{2,40})",
        text, re.IGNORECASE,
    ):
        regs.append({
            "address": m.group(1),
            "name": m.group(2).strip(),
            "description": "",
        })
        if len(regs) >= 50:
            break
    return regs


def _extract_timing(text: str) -> list[dict]:
    constraints: list[dict] = []
    for m in re.finditer(
        r"(\w[\w\s]{2,30}?)\s+(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*(ms|us|ns|MHz|kHz|Hz)",
        text, re.IGNORECASE,
    ):
        constraints.append({
            "parameter": m.group(1).strip(),
            "min": m.group(2),
            "max": m.group(3),
            "unit": m.group(4),
        })
        if len(constraints) >= 20:
            break
    return constraints


def _extract_section(text: str, keywords: list[str]) -> str | None:
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(text), idx + 500)
            return text[start:end].strip()
    return None
