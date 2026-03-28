"""Storage module for persisting and loading Analysis_Run records."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime

from cas.models import BrandMetrics, RunRecord


def save_run(
    brand_metrics: list[BrandMetrics],
    run_date: datetime,
    storage_path: str = "runs.json",
) -> None:
    """Append a RunRecord to the local JSON storage file."""
    record = RunRecord(run_date=run_date, brand_metrics=brand_metrics)
    record_dict = asdict(record)
    # Convert datetime to ISO string
    record_dict["run_date"] = run_date.isoformat()

    existing: list[dict] = []
    if os.path.exists(storage_path):
        with open(storage_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing.append(record_dict)

    with open(storage_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def load_runs(storage_path: str = "runs.json") -> list[RunRecord]:
    """Load all RunRecord objects from the local JSON storage file."""
    if not os.path.exists(storage_path):
        return []

    with open(storage_path, "r", encoding="utf-8") as f:
        raw_records: list[dict] = json.load(f)

    runs: list[RunRecord] = []
    for raw in raw_records:
        brand_metrics = [
            BrandMetrics(
                widget_id=bm["widget_id"],
                total_conversations=bm["total_conversations"],
                drop_off_rate=bm["drop_off_rate"],
                frustration_rate=bm["frustration_rate"],
                response_quality_score=bm["response_quality_score"],
                product_engagement_rate=bm["product_engagement_rate"],
                outlier_flags=bm.get("outlier_flags", []),
            )
            for bm in raw["brand_metrics"]
        ]
        runs.append(
            RunRecord(
                run_date=datetime.fromisoformat(raw["run_date"]),
                brand_metrics=brand_metrics,
            )
        )

    return runs


_TRACKED_METRICS = [
    "drop_off_rate",
    "frustration_rate",
    "response_quality_score",
    "product_engagement_rate",
]


def compute_wow_changes(
    runs: list[RunRecord],
) -> dict[str, dict[str, dict]]:
    """Compute week-over-week metric changes per brand.

    Returns:
        dict[widget_id, dict[metric_name, {"change": float, "flag": str | None}]]
        where flag is "regression" if change < -0.10, "improvement" if change > +0.10, else None
    """
    # Group runs by ISO week key (year, week_number)
    weeks: dict[tuple[int, int], list[RunRecord]] = {}
    for run in runs:
        iso_cal = run.run_date.isocalendar()
        week_key = (iso_cal[0], iso_cal[1])  # (year, week)
        weeks.setdefault(week_key, []).append(run)

    # Sort week keys chronologically
    sorted_week_keys = sorted(weeks.keys())

    if len(sorted_week_keys) < 2:
        return {}

    # Build per-brand, per-week metric snapshots
    # brand_week_metrics[widget_id][week_key] = BrandMetrics
    brand_week_metrics: dict[str, dict[tuple[int, int], BrandMetrics]] = {}
    for week_key, week_runs in weeks.items():
        for run in week_runs:
            for bm in run.brand_metrics:
                brand_week_metrics.setdefault(bm.widget_id, {})[week_key] = bm

    result: dict[str, dict[str, dict]] = {}

    for widget_id, week_map in brand_week_metrics.items():
        # Find the two most recent consecutive weeks for this brand
        brand_weeks = sorted(wk for wk in sorted_week_keys if wk in week_map)
        if len(brand_weeks) < 2:
            continue

        # Take the last two consecutive weeks
        old_key = brand_weeks[-2]
        new_key = brand_weeks[-1]

        old_bm = week_map[old_key]
        new_bm = week_map[new_key]

        metric_changes: dict[str, dict] = {}
        for metric in _TRACKED_METRICS:
            old_val: float = getattr(old_bm, metric)
            new_val: float = getattr(new_bm, metric)

            if old_val == 0:
                continue  # skip division by zero

            change = (new_val - old_val) / old_val
            # Round to avoid floating-point boundary issues (e.g. 0.45/0.5 = -0.0999...)
            change_rounded = round(change, 10)

            if change_rounded <= -0.10:
                flag: str | None = "regression"
            elif change_rounded >= 0.10:
                flag = "improvement"
            else:
                flag = None

            metric_changes[metric] = {"change": change, "flag": flag}

        if metric_changes:
            result[widget_id] = metric_changes

    return result
