"""Report generation for the Conversation Analysis System."""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from cas.models import AggregatedReport


def _default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _report_to_dict(report: AggregatedReport) -> dict:
    d = dataclasses.asdict(report)
    # Convert run_date datetime to ISO string
    if isinstance(d.get("run_date"), datetime):
        d["run_date"] = d["run_date"].isoformat()
    return d


def generate_report(report: AggregatedReport, output_dir: str) -> None:
    """Generate JSON and Markdown reports from an AggregatedReport.

    Args:
        report: The aggregated report data.
        output_dir: Directory where report files will be written.

    Raises:
        IOError: If the output directory is not writable.
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    if not os.access(path, os.W_OK):
        raise IOError(f"Output directory is not writable: {output_dir}")

    # --- JSON output ---
    report_dict = _report_to_dict(report)
    json_path = path / "report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=_default_serializer)

    # --- Markdown output via Jinja2 ---
    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    template = env.get_template("report.md.j2")
    md_content = template.render(report=report, report_dict=report_dict)

    md_path = path / "report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
