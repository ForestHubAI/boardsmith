# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the LLM-based datasheet extraction pipeline.

These tests validate the parsing, section detection, JSON response parsing,
and validation — all without requiring an actual LLM API call.
"""

import json

from boardsmith_fw.knowledge.extractor import (
    DatasheetSections,
    ExtractionResult,
    _build_knowledge_from_dict,
    _extract_section,
    parse_extraction_response,
    prepare_extraction_text,
    save_extracted_knowledge,
)
from boardsmith_fw.models.component_knowledge import InterfaceType

# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------


class TestSectionExtraction:
    def test_extract_section_finds_keywords(self):
        pages = [
            "Page 1: Introduction\nThis is the BME280 sensor.",
            "Page 2: Register Map\nAddress 0xD0 chip_id returns 0x60",
            "Page 3: Timing Characteristics\nMax I2C clock 3.4MHz",
        ]
        result = _extract_section(pages, keywords=["register map"])
        assert "0xD0" in result
        assert "Page 1" not in result

    def test_extract_section_empty_when_no_match(self):
        pages = ["Page 1: General description"]
        result = _extract_section(pages, keywords=["register map"])
        assert result == ""

    def test_extract_section_truncates(self):
        pages = ["Register Map\n" + "x" * 5000]
        result = _extract_section(pages, keywords=["register map"], max_chars=100)
        assert len(result) <= 120  # 100 + truncation message
        assert "[... truncated]" in result

    def test_extract_section_multiple_pages(self):
        pages = [
            "Page 1: Register Map Part 1\nAddr 0x00",
            "Page 2: Other stuff",
            "Page 3: Register Map Part 2\nAddr 0x10",
        ]
        result = _extract_section(pages, keywords=["register map"])
        assert "0x00" in result
        assert "0x10" in result
        assert "Other stuff" not in result


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------


class TestPrepareText:
    def test_combines_sections(self):
        sections = DatasheetSections(
            title="BME280 Datasheet",
            register_map="Register 0xD0 = chip_id",
            timing_electrical="Max I2C freq 3.4MHz",
        )
        text = prepare_extraction_text(sections)
        assert "TITLE" in text
        assert "REGISTER MAP" in text
        assert "TIMING" in text
        assert "BME280" in text

    def test_falls_back_to_full_text(self):
        sections = DatasheetSections(
            full_text="Full datasheet content here with lots of info",
        )
        text = prepare_extraction_text(sections)
        assert "FULL DATASHEET TEXT" in text

    def test_respects_max_total(self):
        sections = DatasheetSections(
            register_map="R" * 20000,
            timing_electrical="T" * 20000,
        )
        text = prepare_extraction_text(sections, max_total=5000)
        assert len(text) <= 5200  # some slack for headers + truncation msg


# ---------------------------------------------------------------------------
# JSON response parsing
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Test parse_extraction_response with realistic LLM outputs."""

    VALID_JSON = json.dumps({
        "name": "BME280",
        "manufacturer": "Bosch Sensortec",
        "mpn": "BME280",
        "description": "Temperature, pressure, humidity sensor",
        "category": "sensor",
        "interface": "I2C",
        "i2c_address": "0x76",
        "spi_mode": 0,
        "registers": [
            {
                "address": "0xD0",
                "name": "chip_id",
                "description": "Returns 0x60",
                "fields": [],
            },
            {
                "address": "0xF4",
                "name": "ctrl_meas",
                "description": "Control measurement",
                "fields": [
                    {
                        "name": "mode",
                        "bits": "1:0",
                        "description": "Operating mode",
                        "default_value": "00",
                    },
                ],
            },
        ],
        "init_sequence": [
            {"order": 1, "reg_addr": "0xE0", "value": "0xB6",
             "description": "Soft reset", "delay_ms": None},
            {"order": 2, "reg_addr": "", "value": "",
             "description": "Wait for reset", "delay_ms": 10},
        ],
        "timing_constraints": [
            {"parameter": "I2C clock", "min": "", "typical": "",
             "max": "3400000", "unit": "Hz"},
        ],
        "notes": ["SDO pin selects address: 0x76 or 0x77"],
    })

    def test_valid_json_parsed(self):
        k = parse_extraction_response(self.VALID_JSON)
        assert k is not None
        assert k.name == "BME280"
        assert k.manufacturer == "Bosch Sensortec"
        assert k.interface == InterfaceType.I2C
        assert k.i2c_address == "0x76"

    def test_registers_parsed(self):
        k = parse_extraction_response(self.VALID_JSON)
        assert len(k.registers) == 2
        assert k.registers[0].address == "0xD0"
        assert k.registers[1].name == "ctrl_meas"
        assert len(k.registers[1].fields) == 1
        assert k.registers[1].fields[0].name == "mode"

    def test_init_sequence_parsed(self):
        k = parse_extraction_response(self.VALID_JSON)
        assert len(k.init_sequence) == 2
        assert k.init_sequence[0].reg_addr == "0xE0"
        assert k.init_sequence[0].value == "0xB6"
        assert k.init_sequence[1].delay_ms == 10

    def test_timing_parsed(self):
        k = parse_extraction_response(self.VALID_JSON)
        assert len(k.timing_constraints) == 1
        assert k.timing_constraints[0].max == "3400000"

    def test_notes_parsed(self):
        k = parse_extraction_response(self.VALID_JSON)
        assert len(k.notes) == 1
        assert "SDO" in k.notes[0]

    def test_markdown_code_fence_stripped(self):
        wrapped = f"```json\n{self.VALID_JSON}\n```"
        k = parse_extraction_response(wrapped)
        assert k is not None
        assert k.name == "BME280"

    def test_invalid_json_returns_none(self):
        errors: list[str] = []
        k = parse_extraction_response("not json at all", errors)
        assert k is None
        assert any("JSON" in e for e in errors)

    def test_partial_json_in_mixed_content(self):
        mixed = f'Here is the result:\n{self.VALID_JSON}\nDone.'
        k = parse_extraction_response(mixed)
        assert k is not None
        assert k.name == "BME280"

    def test_minimal_json(self):
        minimal = json.dumps({
            "name": "UNKNOWN_CHIP",
            "interface": "SPI",
        })
        errors: list[str] = []
        k = parse_extraction_response(minimal, errors)
        assert k is not None
        assert k.name == "UNKNOWN_CHIP"
        assert k.interface == InterfaceType.SPI
        # Should warn about missing data
        assert any("no registers" in e.lower() for e in errors)

    def test_null_values_handled(self):
        data = json.dumps({
            "name": "TestChip",
            "manufacturer": None,
            "interface": "I2C",
            "i2c_address": "0x50",
            "spi_mode": None,
            "registers": None,
            "init_sequence": None,
            "timing_constraints": None,
            "notes": None,
        })
        k = parse_extraction_response(data)
        assert k is not None
        assert k.name == "TestChip"
        assert k.registers == []


# ---------------------------------------------------------------------------
# Knowledge building from dict
# ---------------------------------------------------------------------------


class TestBuildKnowledge:
    def test_interface_enum_mapping(self):
        for iface in ["I2C", "SPI", "UART", "GPIO", "OTHER"]:
            errors: list[str] = []
            k = _build_knowledge_from_dict(
                {"name": "X", "interface": iface}, errors,
            )
            assert k is not None
            assert k.interface.value == iface

    def test_unknown_interface_defaults_to_other(self):
        errors: list[str] = []
        k = _build_knowledge_from_dict(
            {"name": "X", "interface": "FOOBAR"}, errors,
        )
        assert k is not None
        assert k.interface == InterfaceType.OTHER

    def test_timing_values_converted_to_string(self):
        """LLM sometimes returns numbers instead of strings for min/max."""
        errors: list[str] = []
        k = _build_knowledge_from_dict({
            "name": "X",
            "interface": "I2C",
            "timing_constraints": [
                {"parameter": "freq", "min": 100, "max": 400000,
                 "typical": None, "unit": "Hz"},
            ],
        }, errors)
        assert k is not None
        tc = k.timing_constraints[0]
        assert tc.min == "100"
        assert tc.max == "400000"
        assert tc.typical == ""


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------


class TestExtractionResult:
    def test_result_defaults(self):
        r = ExtractionResult()
        assert r.knowledge is None
        assert r.errors == []
        assert r.sections_found == []
        assert r.raw_json == ""

    def test_result_with_knowledge(self):
        r = ExtractionResult()
        r.knowledge = parse_extraction_response(TestParseResponse.VALID_JSON)
        assert r.knowledge is not None
        assert r.knowledge.name == "BME280"


# ---------------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    def test_save_extracted_knowledge(self, tmp_path):
        from boardsmith_fw.knowledge.builtin_db import lookup_builtin

        k = lookup_builtin("BME280")
        k.component_id = "test_component"
        path = save_extracted_knowledge(k, cache_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

        # Should be loadable
        from boardsmith_fw.knowledge.resolver import _load_from_cache

        loaded = _load_from_cache("BME280", tmp_path)
        assert loaded is not None
        assert loaded.name == "BME280"


# ---------------------------------------------------------------------------
# PDF parsing (structural test — no actual PDF needed)
# ---------------------------------------------------------------------------


class TestPDFParsing:
    def test_parse_datasheet_pdf_is_importable(self):
        from boardsmith_fw.knowledge.extractor import parse_datasheet_pdf

        assert callable(parse_datasheet_pdf)

    def test_datasheet_sections_defaults(self):
        s = DatasheetSections()
        assert s.full_text == ""
        assert s.page_count == 0
        assert s.register_map == ""
