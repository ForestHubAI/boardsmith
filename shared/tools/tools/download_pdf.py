# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: download_pdf — download a PDF to local cache."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import ToolContext, ToolResult

log = logging.getLogger(__name__)


@dataclass
class DownloadPDFInput:
    url: str
    filename: str = ""    # optional override; defaults to hash of URL


class DownloadPDFTool:
    """Downloads a PDF from a URL and caches it locally.

    The cached path is returned so subsequent tools (extract_datasheet)
    can read it without re-downloading.
    """

    name = "download_pdf"
    description = (
        "Download a PDF file (e.g. a datasheet) from a URL and save it to the "
        "local cache. Returns the local file path. "
        "Input: {\"url\": \"https://...\", \"filename\": \"optional_name.pdf\"}"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the PDF to download"},
            "filename": {"type": "string", "description": "Optional filename override", "default": ""},
        },
        "required": ["url"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        # Accept dict or dataclass
        if isinstance(input, dict):
            url = input.get("url", "")
            filename = input.get("filename", "")
        else:
            url = getattr(input, "url", "")
            filename = getattr(input, "filename", "")

        if not url:
            return ToolResult(
                success=False,
                data=None,
                source="download_pdf",
                confidence=0.0,
                error="No URL provided",
            )

        # Determine local path
        pdf_cache = context.cache_dir / "datasheets"
        pdf_cache.mkdir(parents=True, exist_ok=True)

        if not filename:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            # Try to get a nice name from the URL
            url_basename = url.rstrip("/").split("/")[-1]
            if url_basename.endswith(".pdf"):
                filename = url_basename
            else:
                filename = f"datasheet_{url_hash}.pdf"

        local_path = pdf_cache / filename

        # Return cached file if already downloaded
        if local_path.exists() and local_path.stat().st_size > 1024:
            log.debug("PDF cache hit: %s", local_path)
            return ToolResult(
                success=True,
                data=str(local_path),
                source=f"cache:{url}",
                confidence=1.0,
                metadata={"url": url, "path": str(local_path), "cached": True},
            )

        # Download
        try:
            import httpx
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                source="download_pdf",
                confidence=0.0,
                error="httpx not installed (pip install httpx)",
            )

        try:
            log.info("Downloading PDF: %s → %s", url, local_path.name)
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Boardsmith/0.1 (hardware research)"})
                resp.raise_for_status()
                local_path.write_bytes(resp.content)

            size_kb = local_path.stat().st_size // 1024
            log.info("Downloaded %d KB → %s", size_kb, local_path)

            return ToolResult(
                success=True,
                data=str(local_path),
                source=f"download:{url}",
                confidence=1.0,
                metadata={"url": url, "path": str(local_path), "size_kb": size_kb, "cached": False},
            )

        except Exception as e:
            log.warning("PDF download failed: %s — %s", url, e)
            return ToolResult(
                success=False,
                data=None,
                source="download_pdf",
                confidence=0.0,
                error=f"Download failed: {e}",
            )
