"""Unit tests for cas/storage.py — save_run, load_runs, compute_wow_changes."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from cas.models import BrandMetrics, RunRecord
from cas.storage import compute_wow_changes, load_runs, save_run


def _make_brand(widget_id: str, **overrides) -> BrandMetrics:
    defaults = dict(
        total_conversations=100,
        drop_off_rate=0.5,
        frustration_rate=0.3,
        response_quality_score=0.7,
        product_engagement_rate=0.4,
        outlier_flags=[],
    )
    defaults.update(overrides)
    return BrandMetrics(widget_id=widget_id, **defaults)


def _make_run(run_date: datetime, brands: list[BrandMetrics] | None = None) -> RunRecord:
    if brands is None:
        brands = [_make_brand("brand_a")]
    return RunRecord(run_date=run_date, brand_metrics=brands)


# ---------------------------------------------------------------------------
# save_run / load_runs
# ---------------------------------------------------------------------------

def test_save_then_load_returns_matching_record():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    os.unlink(path)  # ensure file doesn't exist yet

    try:
        run_date = datetime(2024, 1, 15, 12, 0, 0)
        brand = _make_brand("brand_x", drop_off_rate=0.25)
        save_run([brand], run_date, storage_path=path)

        runs = load_runs(storage_path=path)
        assert len(runs) == 1
        loaded = runs[0]
        assert loaded.run_date == run_date
        assert len(loaded.brand_metrics) == 1
        assert loaded.brand_metrics[0].widget_id == "brand_x"
        assert loaded.brand_metrics[0].drop_off_rate == 0.25
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_load_runs_returns_empty_list_when_file_missing():
    runs = load_runs(storage_path="/tmp/nonexistent_cas_runs_xyz.json")
    assert runs == []


def test_multiple_saves_accumulate_records():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    os.unlink(path)

    try:
        dates = [datetime(2024, 1, 7), datetime(2024, 1, 14), datetime(2024, 1, 21)]
        for d in dates:
            save_run([_make_brand("brand_a")], d, storage_path=path)

        runs = load_runs(storage_path=path)
        assert len(runs) == 3
        loaded_dates = [r.run_date for r in runs]
        assert loaded_dates == dates
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ---------------------------------------------------------------------------
# compute_wow_changes — flag thresholds
# ---------------------------------------------------------------------------

def _two_week_runs(
    old_value: float,
    new_value: float,
    metric: str = "drop_off_rate",
    widget_id: str = "brand_a",
) -> list[RunRecord]:
    """Helper: two runs in consecutive ISO weeks with the given metric values."""
    # Week 1: Monday of ISO week 2, 2024
    week1_date = datetime(2024, 1, 8)   # ISO week 2
    week2_date = datetime(2024, 1, 15)  # ISO week 3

    old_brand = _make_brand(widget_id, **{metric: old_value})
    new_brand = _make_brand(widget_id, **{metric: new_value})

    return [
        RunRecord(run_date=week1_date, brand_metrics=[old_brand]),
        RunRecord(run_date=week2_date, brand_metrics=[new_brand]),
    ]


def test_wow_regression_flag_at_exactly_minus_10_percent():
    # 0.5 → 0.45 = -10% change → should flag "regression"
    runs = _two_week_runs(old_value=0.5, new_value=0.45)
    result = compute_wow_changes(runs)
    assert "brand_a" in result
    entry = result["brand_a"]["drop_off_rate"]
    assert pytest.approx(entry["change"], rel=1e-6) == -0.10
    assert entry["flag"] == "regression"


def test_wow_improvement_flag_at_exactly_plus_10_percent():
    # 0.5 → 0.55 = +10% change → should flag "improvement"
    runs = _two_week_runs(old_value=0.5, new_value=0.55)
    result = compute_wow_changes(runs)
    assert "brand_a" in result
    entry = result["brand_a"]["drop_off_rate"]
    assert pytest.approx(entry["change"], rel=1e-6) == 0.10
    assert entry["flag"] == "improvement"


def test_wow_no_flag_within_threshold():
    # 0.5 → 0.52 = +4% change → no flag
    runs = _two_week_runs(old_value=0.5, new_value=0.52)
    result = compute_wow_changes(runs)
    assert "brand_a" in result
    entry = result["brand_a"]["drop_off_rate"]
    assert entry["flag"] is None


def test_wow_insufficient_history_skips_brand():
    # Only one week of data — no WoW possible
    single_run = RunRecord(
        run_date=datetime(2024, 1, 8),
        brand_metrics=[_make_brand("brand_a")],
    )
    result = compute_wow_changes([single_run])
    assert result == {}


def test_wow_no_runs_returns_empty():
    result = compute_wow_changes([])
    assert result == {}


def test_wow_brand_missing_in_one_week_skips():
    # brand_b only appears in week 2, not week 1 → skip
    week1 = RunRecord(
        run_date=datetime(2024, 1, 8),
        brand_metrics=[_make_brand("brand_a")],
    )
    week2 = RunRecord(
        run_date=datetime(2024, 1, 15),
        brand_metrics=[_make_brand("brand_a"), _make_brand("brand_b")],
    )
    result = compute_wow_changes([week1, week2])
    assert "brand_b" not in result
    assert "brand_a" in result
