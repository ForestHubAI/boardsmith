# SPDX-License-Identifier: AGPL-3.0-or-later
"""Constraint Report — export validation results as JSON or HTML.

Usage:
    from boardsmith_fw.analysis.constraint_report import export_json, export_html

    json_str = export_json(hir)
    html_str = export_html(hir)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from boardsmith_fw.models.hir import HIR, ConstraintSeverity, ConstraintStatus


def export_json(hir: HIR) -> str:
    """Export constraint validation results as JSON."""
    report = _build_report_data(hir)
    return json.dumps(report, indent=2)


def export_html(hir: HIR) -> str:
    """Export constraint validation results as a standalone HTML report."""
    data = _build_report_data(hir)
    return _render_html(data)


def _build_report_data(hir: HIR) -> dict:
    """Build structured report data from HIR constraints."""
    constraints = hir.constraints

    by_category: dict[str, list[dict]] = {}
    for c in constraints:
        entry = {
            "id": c.id,
            "description": c.description,
            "severity": c.severity.value,
            "status": c.status.value,
            "affected_components": c.affected_components,
        }
        by_category.setdefault(c.category, []).append(entry)

    pass_count = sum(1 for c in constraints if c.status == ConstraintStatus.PASS)
    fail_count = sum(1 for c in constraints if c.status == ConstraintStatus.FAIL)
    unknown_count = sum(1 for c in constraints if c.status == ConstraintStatus.UNKNOWN)
    error_count = sum(
        1 for c in constraints
        if c.status == ConstraintStatus.FAIL and c.severity == ConstraintSeverity.ERROR
    )
    warning_count = sum(
        1 for c in constraints
        if c.status == ConstraintStatus.FAIL and c.severity == ConstraintSeverity.WARNING
    )

    return {
        "boardsmith_fw_version": "0.5.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": hir.source,
        "summary": {
            "total": len(constraints),
            "pass": pass_count,
            "fail": fail_count,
            "unknown": unknown_count,
            "errors": error_count,
            "warnings": warning_count,
            "valid": error_count == 0,
        },
        "categories": by_category,
        "bus_contracts": len(hir.bus_contracts),
        "init_contracts": len(hir.init_contracts),
        "electrical_specs": len(hir.electrical_specs),
    }


def _render_html(data: dict) -> str:
    """Render the report data as standalone HTML."""
    summary = data["summary"]
    status_class = "pass" if summary["valid"] else "fail"

    # Build constraint rows
    rows = []
    for category, checks in sorted(data["categories"].items()):
        for c in checks:
            s = c["status"]
            sev = c["severity"]
            cls = "pass" if s == "pass" else ("fail" if sev == "error" else "warn")
            rows.append(
                f'<tr class="{cls}">'
                f"<td>{category}</td>"
                f"<td>{c['id']}</td>"
                f"<td>{c['description']}</td>"
                f"<td>{sev}</td>"
                f"<td>{s.upper()}</td>"
                f"</tr>"
            )
    table_body = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>boardsmith-fw Constraint Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; }}
h1 {{ font-size: 1.5rem; }}
.summary {{ display: flex; gap: 1rem; margin: 1rem 0; }}
.summary .card {{ padding: 0.8rem 1.2rem; border-radius: 6px; font-weight: bold; }}
.card.pass {{ background: #d4edda; color: #155724; }}
.card.fail {{ background: #f8d7da; color: #721c24; }}
.card.warn {{ background: #fff3cd; color: #856404; }}
.card.info {{ background: #e2e3e5; color: #383d41; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: 0.9rem; }}
th {{ background: #343a40; color: #fff; text-align: left; padding: 0.5rem; }}
td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid #dee2e6; }}
tr.pass td {{ background: #f8fff8; }}
tr.fail td {{ background: #fff5f5; }}
tr.warn td {{ background: #fffcf0; }}
</style>
</head>
<body>
<h1>boardsmith-fw Constraint Report</h1>
<p>Source: <strong>{data['source']}</strong> | Generated: {data['generated_at'][:19]}</p>
<p>HIR: {data['bus_contracts']} bus contracts, \
{data['init_contracts']} init contracts, \
{data['electrical_specs']} electrical specs</p>

<div class="summary">
  <div class="card {status_class}">{'VALID' if summary['valid'] else 'INVALID'}</div>
  <div class="card pass">{summary['pass']} pass</div>
  <div class="card fail">{summary['errors']} errors</div>
  <div class="card warn">{summary['warnings']} warnings</div>
  <div class="card info">{summary['unknown']} unknown</div>
</div>

<table>
<thead><tr><th>Category</th><th>ID</th><th>Description</th><th>Severity</th><th>Status</th></tr></thead>
<tbody>
{table_body}
</tbody>
</table>
</body>
</html>"""
