# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLM-based datasheet extraction pipeline.

Pipeline: PDF/text → section detection → LLM extraction → validation → ComponentKnowledge

Usage:
    # From PDF
    knowledge = await extract_from_pdf(Path("BME280.pdf"))

    # From raw text
    knowledge = await extract_from_text(datasheet_text, hint_name="BME280")

    # Offline (no LLM): just parse PDF and identify sections
    sections = parse_datasheet_pdf(Path("BME280.pdf"))
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from boardsmith_fw.knowledge.prompts import EXTRACTION_PROMPT, SYSTEM_PROMPT
from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    RegisterField,
    RegisterInfo,
    TimingConstraint,
)

# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

@dataclass
class DatasheetSections:
    """Identified sections from a datasheet."""

    full_text: str = ""
    title: str = ""
    pinout: str = ""
    register_map: str = ""
    init_sequence: str = ""
    timing_electrical: str = ""
    application_circuit: str = ""
    page_count: int = 0


def parse_datasheet_pdf(
    pdf_path: Path,
    max_pages: int = 40,
) -> DatasheetSections:
    """Extract text from PDF and identify datasheet sections.

    Uses pdfplumber for text extraction. Falls back gracefully
    if pdfplumber is not installed.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        msg = (
            "pdfplumber is required for PDF extraction. "
            "Install with: pip install boardsmith[llm]"
        )
        raise ImportError(msg) from exc

    sections = DatasheetSections()
    pages_text: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        sections.page_count = len(pdf.pages)
        limit = min(max_pages, len(pdf.pages))

        for page in pdf.pages[:limit]:
            text = page.extract_text() or ""
            pages_text.append(text)

    sections.full_text = "\n\n".join(pages_text)

    # Title: usually first meaningful line
    for line in sections.full_text.split("\n")[:20]:
        stripped = line.strip()
        if len(stripped) > 5 and not stripped.startswith("©"):
            sections.title = stripped
            break

    # Section detection by keyword scanning
    sections.register_map = _extract_section(
        pages_text,
        keywords=["register map", "register table", "register description",
                   "register address", "memory map", "command table"],
        max_chars=12000,
    )

    sections.timing_electrical = _extract_section(
        pages_text,
        keywords=["electrical characteristics", "timing characteristics",
                   "dc characteristics", "ac characteristics",
                   "absolute maximum", "recommended operating"],
        max_chars=8000,
    )

    sections.pinout = _extract_section(
        pages_text,
        keywords=["pin description", "pin configuration", "pin assignment",
                   "pin function", "pinout", "pin name"],
        max_chars=5000,
    )

    sections.init_sequence = _extract_section(
        pages_text,
        keywords=["initialization", "power-on", "startup sequence",
                   "configuration sequence", "quick start",
                   "getting started", "application information"],
        max_chars=6000,
    )

    sections.application_circuit = _extract_section(
        pages_text,
        keywords=["application circuit", "typical application",
                   "reference design", "application schematic"],
        max_chars=4000,
    )

    return sections


def _extract_section(
    pages: list[str],
    keywords: list[str],
    max_chars: int = 8000,
) -> str:
    """Find pages containing any keyword and return their text, capped."""
    found_pages: list[str] = []

    for page_text in pages:
        lower = page_text.lower()
        if any(kw in lower for kw in keywords):
            found_pages.append(page_text)

    combined = "\n\n".join(found_pages)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n[... truncated]"
    return combined


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

def prepare_extraction_text(
    sections: DatasheetSections,
    max_total: int = 24000,
) -> str:
    """Combine the most relevant sections into a single extraction prompt.

    Prioritizes register map and timing over other sections.
    """
    parts: list[tuple[str, str]] = []

    if sections.title:
        parts.append(("TITLE", sections.title))

    # Priority order for context budget
    for label, text in [
        ("REGISTER MAP", sections.register_map),
        ("TIMING / ELECTRICAL", sections.timing_electrical),
        ("INITIALIZATION", sections.init_sequence),
        ("PINOUT", sections.pinout),
        ("APPLICATION", sections.application_circuit),
    ]:
        if text.strip():
            parts.append((label, text))

    # If sections are empty, fall back to full text
    section_text = "\n".join(f for _, f in parts if f)
    if len(section_text) < 200 and sections.full_text:
        parts = [("FULL DATASHEET TEXT", sections.full_text)]

    # Build combined text within budget
    result_parts: list[str] = []
    total = 0
    for label, text in parts:
        chunk = f"=== {label} ===\n{text}"
        if total + len(chunk) > max_total:
            remaining = max_total - total
            if remaining > 200:
                chunk = chunk[:remaining] + "\n[... truncated]"
                result_parts.append(chunk)
            break
        result_parts.append(chunk)
        total += len(chunk)

    return "\n\n".join(result_parts)


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """Result of a datasheet extraction attempt."""

    knowledge: ComponentKnowledge | None = None
    raw_json: str = ""
    errors: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)
    model_used: str = ""
    token_estimate: int = 0


async def extract_from_pdf(
    pdf_path: Path,
    model: str = "gpt-4o",
    max_pages: int = 40,
) -> ExtractionResult:
    """Full pipeline: PDF → sections → LLM → ComponentKnowledge."""
    result = ExtractionResult()

    # Step 1: Parse PDF
    try:
        sections = parse_datasheet_pdf(pdf_path, max_pages=max_pages)
    except Exception as e:
        result.errors.append(f"PDF parse error: {e}")
        return result

    result.sections_found = [
        name for name, text in [
            ("register_map", sections.register_map),
            ("timing_electrical", sections.timing_electrical),
            ("pinout", sections.pinout),
            ("init_sequence", sections.init_sequence),
            ("application_circuit", sections.application_circuit),
        ] if text.strip()
    ]

    # Step 2: Prepare text
    extraction_text = prepare_extraction_text(sections)
    result.token_estimate = len(extraction_text) // 4  # rough estimate

    # Step 3: LLM extraction
    return await _run_llm_extraction(
        extraction_text,
        model=model,
        result=result,
    )


async def extract_from_text(
    datasheet_text: str,
    model: str = "gpt-4o",
    hint_name: str = "",
) -> ExtractionResult:
    """Extract ComponentKnowledge from raw datasheet text."""
    result = ExtractionResult()

    text = datasheet_text
    if hint_name:
        text = f"Component: {hint_name}\n\n{text}"

    result.token_estimate = len(text) // 4
    return await _run_llm_extraction(text, model=model, result=result)


async def _run_llm_extraction(
    text: str,
    model: str,
    result: ExtractionResult,
) -> ExtractionResult:
    """Call LLMGateway and parse the response into ComponentKnowledge."""
    try:
        from llm.gateway import get_default_gateway
        from llm.types import Message, TaskType
    except ImportError:
        result.errors.append("shared/llm not available in PYTHONPATH")
        return result

    gateway = get_default_gateway()
    if not gateway.is_llm_available():
        result.errors.append(
            "No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )
        return result

    prompt = EXTRACTION_PROMPT.replace("{datasheet_text}", text)

    try:
        response = await gateway.complete(
            task=TaskType.DATASHEET_EXTRACT,
            messages=[Message(role="user", content=prompt)],
            system=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=4000,
            model_override=model if model != "gpt-4o" else None,
        )

        if response.skipped or not response.content:
            result.errors.append("LLM returned empty response or was skipped")
            return result

        result.raw_json = response.content
        result.model_used = response.model

    except Exception as e:
        result.errors.append(f"LLM API error: {e}")
        return result

    # Parse JSON response
    result.knowledge = parse_extraction_response(result.raw_json, result.errors)
    return result


# ---------------------------------------------------------------------------
# Response parsing & validation
# ---------------------------------------------------------------------------

def parse_extraction_response(
    raw: str,
    errors: list[str] | None = None,
) -> ComponentKnowledge | None:
    """Parse LLM JSON response into a validated ComponentKnowledge object.

    This function is also useful for testing without an actual LLM call.
    """
    if errors is None:
        errors = []

    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove ```json and trailing ```
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse error: {e}")
        # Try to extract JSON from mixed content
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        else:
            return None

    return _build_knowledge_from_dict(data, errors)


def _build_knowledge_from_dict(
    data: dict,
    errors: list[str],
) -> ComponentKnowledge | None:
    """Convert a raw dict (from LLM JSON) into a ComponentKnowledge."""
    try:
        # Map interface string to enum
        iface_str = (data.get("interface") or "OTHER").upper()
        interface = InterfaceType.OTHER
        for it in InterfaceType:
            if it.value == iface_str:
                interface = it
                break

        # Build registers
        registers: list[RegisterInfo] = []
        for reg in data.get("registers") or []:
            fields = []
            for f in reg.get("fields") or []:
                fields.append(RegisterField(
                    name=f.get("name", ""),
                    bits=f.get("bits", ""),
                    description=f.get("description", ""),
                    default_value=f.get("default_value", ""),
                ))
            registers.append(RegisterInfo(
                address=reg.get("address", ""),
                name=reg.get("name", ""),
                description=reg.get("description", ""),
                fields=fields,
            ))

        # Build init sequence
        init_seq: list[InitStep] = []
        for step in data.get("init_sequence") or []:
            init_seq.append(InitStep(
                order=step.get("order", len(init_seq) + 1),
                reg_addr=step.get("reg_addr", ""),
                value=step.get("value", ""),
                description=step.get("description", ""),
                delay_ms=step.get("delay_ms"),
            ))

        # Build timing constraints
        timing: list[TimingConstraint] = []
        for tc in data.get("timing_constraints") or []:
            timing.append(TimingConstraint(
                parameter=tc.get("parameter", ""),
                min=str(tc.get("min", "") or ""),
                typical=str(tc.get("typical", "") or ""),
                max=str(tc.get("max", "") or ""),
                unit=tc.get("unit", ""),
            ))

        knowledge = ComponentKnowledge(
            version="1.0.0",
            component_id="",
            name=data.get("name") or "UNKNOWN",
            manufacturer=data.get("manufacturer") or "",
            mpn=data.get("mpn") or "",
            description=data.get("description") or "",
            category=data.get("category") or "other",
            interface=interface,
            i2c_address=data.get("i2c_address"),
            spi_mode=data.get("spi_mode"),
            registers=registers,
            init_sequence=init_seq,
            timing_constraints=timing,
            notes=data.get("notes") or [],
        )

        # Validation warnings
        if not knowledge.registers:
            errors.append("Warning: no registers extracted")
        if not knowledge.init_sequence:
            errors.append("Warning: no init sequence extracted")
        if not knowledge.timing_constraints:
            errors.append("Warning: no timing constraints extracted")
        if knowledge.name == "UNKNOWN":
            errors.append("Warning: component name not identified")

        return knowledge

    except Exception as e:
        errors.append(f"Knowledge build error: {e}")
        return None


# ---------------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------------

def save_extracted_knowledge(
    knowledge: ComponentKnowledge,
    cache_dir: Path | None = None,
) -> Path:
    """Save extracted knowledge to the local cache."""
    from boardsmith_fw.knowledge.resolver import save_to_cache

    if cache_dir is None:
        cache_dir = Path.home() / ".boardsmith-fw" / "knowledge"
    return save_to_cache(knowledge, cache_dir)
