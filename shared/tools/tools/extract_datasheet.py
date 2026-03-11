# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: extract_datasheet — PDF → structured component specs via LLM."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import ToolContext, ToolResult

log = logging.getLogger(__name__)


@dataclass
class ExtractDatasheetInput:
    pdf_path: str          # local file path
    component_name: str = ""   # optional hint for the LLM


class ExtractDatasheetTool:
    """Extracts structured component specs from a local datasheet PDF.

    Uses the compiler's extractor pipeline (PDF parsing + LLM extraction).
    Returns a JSON dict compatible with the shared/knowledge schema.
    """

    name = "extract_datasheet"
    description = (
        "Extract component specifications from a local PDF datasheet. "
        "Returns a JSON object with mpn, interface, I2C address, voltage range, "
        "and other electrical specs. "
        "Input: {\"pdf_path\": \"/path/to/file.pdf\", \"component_name\": \"SCD41\"}"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "pdf_path": {"type": "string", "description": "Local file path to the PDF datasheet"},
            "component_name": {"type": "string", "description": "Optional component name hint", "default": ""},
        },
        "required": ["pdf_path"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        # Accept dict or dataclass
        if isinstance(input, dict):
            pdf_path_str = input.get("pdf_path", "")
            component_name = input.get("component_name", "")
        else:
            pdf_path_str = getattr(input, "pdf_path", "")
            component_name = getattr(input, "component_name", "")

        if not pdf_path_str:
            return ToolResult(
                success=False,
                data=None,
                source="extract_datasheet",
                confidence=0.0,
                error="No pdf_path provided",
            )

        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            return ToolResult(
                success=False,
                data=None,
                source="extract_datasheet",
                confidence=0.0,
                error=f"PDF not found: {pdf_path}",
            )

        if context.no_llm:
            return ToolResult(
                success=False,
                data=None,
                source="extract_datasheet",
                confidence=0.0,
                error="LLM disabled (--no-llm), cannot extract from datasheet",
            )

        # Try compiler extractor first (full pipeline)
        try:
            result = await self._extract_via_compiler(pdf_path, component_name)
            if result:
                return result
        except ImportError:
            log.debug("Compiler extractor not available, using shared LLM path")

        # Fallback: shared LLM path (simpler, no compiler dependency)
        return await self._extract_via_shared_llm(pdf_path, component_name, context)

    async def _extract_via_compiler(self, pdf_path: Path, component_name: str) -> ToolResult | None:
        """Use the compiler's full extraction pipeline."""
        from boardsmith_fw.knowledge.extractor import extract_from_pdf

        extraction = await extract_from_pdf(pdf_path)

        if extraction.errors and not extraction.knowledge:
            log.warning("Compiler extractor errors: %s", extraction.errors)
            return None

        if not extraction.knowledge:
            return None

        k = extraction.knowledge
        data = {
            "mpn": k.mpn or component_name,
            "name": k.name,
            "manufacturer": k.manufacturer,
            "category": k.category,
            "interface": k.interface.value if k.interface else "OTHER",
            "interface_types": [k.interface.value] if k.interface else [],
            "i2c_address": k.i2c_address,
            "electrical_ratings": {},
            "known_i2c_addresses": [k.i2c_address] if k.i2c_address else [],
            "registers_count": len(k.registers),
            "init_steps_count": len(k.init_sequence),
            "model_used": extraction.model_used,
        }

        confidence = 0.75 if (k.registers and k.init_sequence) else 0.55

        return ToolResult(
            success=True,
            data=data,
            source=f"compiler_extractor:{pdf_path.name}",
            confidence=confidence,
            metadata={
                "sections_found": extraction.sections_found,
                "model": extraction.model_used,
                "warnings": extraction.errors,
            },
        )

    async def _extract_via_shared_llm(
        self, pdf_path: Path, component_name: str, context: ToolContext
    ) -> ToolResult:
        """Simplified extraction using shared LLM gateway directly."""
        # Parse PDF text
        try:
            import pdfplumber
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                source="extract_datasheet",
                confidence=0.0,
                error="pdfplumber not installed — install with: pip install boardsmith[llm]",
            )

        try:
            pages_text: list[str] = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:30]:  # limit pages
                    text = page.extract_text() or ""
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text)[:20000]  # cap at 20k chars
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                source="extract_datasheet",
                confidence=0.0,
                error=f"PDF parse error: {e}",
            )

        # Call LLM
        from llm.types import Message, TaskType

        system = (
            "You are a hardware component expert. Extract the key electrical specs "
            "from the provided datasheet text. Return ONLY a JSON object with these fields: "
            "mpn, name, manufacturer, category, interface (I2C/SPI/UART/GPIO), "
            "i2c_address (hex string or null), vdd_min, vdd_max, current_ma_typ, "
            "interface_types (list), known_i2c_addresses (list of hex strings), tags (list)."
        )

        hint = f"Component: {component_name}\n\n" if component_name else ""
        user = f"{hint}Datasheet text (excerpt):\n{full_text}"

        try:
            response = await context.llm_gateway.complete(
                task=TaskType.DATASHEET_EXTRACT,
                messages=[Message(role="user", content=user)],
                system=system,
                temperature=0.1,
                max_tokens=2000,
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, source="extract_datasheet",
                confidence=0.0, error=f"LLM error: {e}",
            )

        if response.skipped or not response.content:
            return ToolResult(
                success=False, data=None, source="extract_datasheet",
                confidence=0.0, error="LLM returned empty",
            )

        # Parse JSON from response
        raw = response.content.strip()
        if raw.startswith("```"):
            import re
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
            confidence = 0.65
            return ToolResult(
                success=True,
                data=data,
                source=f"llm_extract:{pdf_path.name}",
                confidence=confidence,
                metadata={"model": response.model, "pdf": str(pdf_path)},
            )
        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                data={"raw_text": raw},
                source="extract_datasheet",
                confidence=0.30,
                error="LLM response was not valid JSON",
            )
