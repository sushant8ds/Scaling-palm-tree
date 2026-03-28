"""Tests for cas/reporter.py."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from cas.models import (
    AggregatedReport,
    BrandMetrics,
    FlaggedConversation,
    FlaggedResponse,
    ReportSummary,
)
from cas.reporter import generate_report


def _make_empty_report() -> AggregatedReport:
    return AggregatedReport(
        run_date=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        filters_applied={},
        brand_metrics=[],
        flagged_conversations=[],
        systemic_issues=[],
        brand_specific_issues={},
        summary=ReportSummary(
            total_conversations=0,
            total_brands=0,
            overall_drop_off_rate=0.0,
            top_3_issues=[],
        ),
    )


def _make_full_report() -> AggregatedReport:
    flagged_response = FlaggedResponse(
        message_id="msg-1",
        flag_type="irrelevant",
        confidence=0.85,
        reason="Response did not address user query",
    )
    flagged_conv = FlaggedConversation(
        conversation_id="conv-abc",
        widget_id="brand-x",
        flag_reason="drop_off, high_frustration",
        drop_off=True,
        frustration_score=0.75,
        flagged_responses=[flagged_response],
    )
    brand_metric = BrandMetrics(
        widget_id="brand-x",
        total_conversations=50,
        drop_off_rate=0.2,
        frustration_rate=0.1,
        response_quality_score=0.85,
        product_engagement_rate=0.4,
        outlier_flags=["drop_off_rate"],
    )
    return AggregatedReport(
        run_date=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        filters_applied={"widget_id": "brand-x"},
        brand_metrics=[brand_metric],
        flagged_conversations=[flagged_conv],
        systemic_issues=["high_drop_off"],
        brand_specific_issues={"brand-x": ["low_product_engagement"]},
        summary=ReportSummary(
            total_conversations=50,
            total_brands=1,
            overall_drop_off_rate=0.2,
            top_3_issues=["high_drop_off", "high_frustration", "low_response_quality"],
        ),
    )


def test_output_files_are_created(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()


def test_output_directory_is_created(tmp_path):
    new_dir = tmp_path / "nested" / "output"
    report = _make_full_report()
    generate_report(report, str(new_dir))

    assert new_dir.is_dir()
    assert (new_dir / "report.json").exists()
    assert (new_dir / "report.md").exists()


def test_json_contains_required_top_level_keys(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    required_keys = {
        "run_date",
        "filters_applied",
        "summary",
        "brand_metrics",
        "flagged_conversations",
        "systemic_issues",
        "brand_specific_issues",
    }
    assert required_keys.issubset(data.keys())


def test_json_summary_structure(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    summary = data["summary"]
    assert summary["total_conversations"] == 50
    assert summary["total_brands"] == 1
    assert summary["overall_drop_off_rate"] == pytest.approx(0.2)
    assert len(summary["top_3_issues"]) == 3


def test_json_brand_metrics_structure(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    assert len(data["brand_metrics"]) == 1
    bm = data["brand_metrics"][0]
    assert bm["widget_id"] == "brand-x"
    assert "drop_off_rate" in bm
    assert "frustration_rate" in bm
    assert "response_quality_score" in bm
    assert "product_engagement_rate" in bm
    assert "outlier_flags" in bm


def test_json_flagged_conversations_structure(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    assert len(data["flagged_conversations"]) == 1
    fc = data["flagged_conversations"][0]
    assert fc["conversation_id"] == "conv-abc"
    assert fc["widget_id"] == "brand-x"
    assert "flag_reason" in fc
    assert "drop_off" in fc
    assert "frustration_score" in fc
    assert "flagged_responses" in fc


def test_json_run_date_is_iso_string(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    # Should be a valid ISO datetime string
    run_date = data["run_date"]
    assert isinstance(run_date, str)
    # Should be parseable
    parsed = datetime.fromisoformat(run_date)
    assert parsed.year == 2024


def test_markdown_contains_report_header(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    content = (tmp_path / "report.md").read_text()
    assert "# Conversation Analysis Report" in content


def test_markdown_contains_summary_section(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    content = (tmp_path / "report.md").read_text()
    assert "Summary" in content
    assert "50" in content  # total conversations


def test_markdown_contains_brand_metrics(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    content = (tmp_path / "report.md").read_text()
    assert "brand-x" in content
    assert "Per-Brand Metrics" in content


def test_markdown_contains_flagged_conversations(tmp_path):
    report = _make_full_report()
    generate_report(report, str(tmp_path))

    content = (tmp_path / "report.md").read_text()
    assert "Flagged Conversations" in content
    assert "conv-abc" in content


def test_zero_results_report_contains_no_conversations_message(tmp_path):
    report = _make_empty_report()
    generate_report(report, str(tmp_path))

    content = (tmp_path / "report.md").read_text()
    assert "No conversations matched the specified filters" in content


def test_zero_results_report_json_has_empty_collections(tmp_path):
    report = _make_empty_report()
    generate_report(report, str(tmp_path))

    with open(tmp_path / "report.json") as f:
        data = json.load(f)

    assert data["brand_metrics"] == []
    assert data["flagged_conversations"] == []
    assert data["summary"]["total_conversations"] == 0


def test_ioerror_raised_when_directory_not_writable(tmp_path):
    report = _make_full_report()
    with patch("os.access", return_value=False):
        with pytest.raises(IOError, match=str(tmp_path)):
            generate_report(report, str(tmp_path))
