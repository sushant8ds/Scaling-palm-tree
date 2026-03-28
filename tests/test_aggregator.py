"""Unit tests for cas/aggregator.py."""

from __future__ import annotations

import pytest

from cas.aggregator import aggregate
from cas.models import AnalysisResult, FlaggedResponse


def make_result(
    conversation_id: str,
    widget_id: str,
    is_drop_off: bool = False,
    frustration_score: float = 0.0,
    flagged_responses: list[FlaggedResponse] | None = None,
    product_engagement: bool = False,
    low_engagement_product_rec: bool = False,
) -> AnalysisResult:
    return AnalysisResult(
        conversation_id=conversation_id,
        widget_id=widget_id,
        topic_categories=[],
        is_drop_off=is_drop_off,
        is_unanswered=False,
        frustration_score=frustration_score,
        flagged_responses=flagged_responses or [],
        product_engagement=product_engagement,
        low_engagement_product_rec=low_engagement_product_rec,
    )


def make_flag() -> FlaggedResponse:
    return FlaggedResponse(message_id="m1", flag_type="irrelevant", confidence=0.9, reason="test")


# --- Empty results ---

def test_empty_results_returns_well_formed_report():
    report = aggregate([])
    assert report.summary.total_conversations == 0
    assert report.summary.total_brands == 0
    assert report.summary.overall_drop_off_rate == 0.0
    assert report.summary.top_3_issues == []
    assert report.brand_metrics == []
    assert report.flagged_conversations == []
    assert report.systemic_issues == []
    assert report.brand_specific_issues == {}


def test_empty_results_with_filters_applied():
    filters = {"widget_id": "brand_x"}
    report = aggregate([], filters_applied=filters)
    assert report.filters_applied == filters


# --- Single-brand metrics ---

def test_single_brand_drop_off_rate():
    results = [
        make_result("c1", "brand_a", is_drop_off=True),
        make_result("c2", "brand_a", is_drop_off=True),
        make_result("c3", "brand_a", is_drop_off=False),
        make_result("c4", "brand_a", is_drop_off=False),
    ]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    assert bm.drop_off_rate == pytest.approx(0.5)


def test_single_brand_frustration_rate():
    results = [
        make_result("c1", "brand_a", frustration_score=0.8),
        make_result("c2", "brand_a", frustration_score=0.6),
        make_result("c3", "brand_a", frustration_score=0.3),
        make_result("c4", "brand_a", frustration_score=0.1),
    ]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    # 2 out of 4 have frustration_score > 0.5
    assert bm.frustration_rate == pytest.approx(0.5)


def test_single_brand_product_engagement_rate():
    results = [
        make_result("c1", "brand_a", product_engagement=True),
        make_result("c2", "brand_a", product_engagement=False),
        make_result("c3", "brand_a", product_engagement=False),
        make_result("c4", "brand_a", product_engagement=False),
    ]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    assert bm.product_engagement_rate == pytest.approx(0.25)


# --- Response quality score ---

def test_response_quality_score_no_flagged_responses():
    results = [make_result(f"c{i}", "brand_a") for i in range(5)]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    assert bm.response_quality_score == pytest.approx(1.0)


def test_response_quality_score_all_flagged():
    results = [make_result(f"c{i}", "brand_a", flagged_responses=[make_flag()]) for i in range(5)]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    assert bm.response_quality_score == pytest.approx(0.0)


def test_response_quality_score_partial_flagged():
    results = [
        make_result("c1", "brand_a", flagged_responses=[make_flag()]),
        make_result("c2", "brand_a", flagged_responses=[make_flag()]),
        make_result("c3", "brand_a"),
        make_result("c4", "brand_a"),
    ]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    # 2 flagged out of 4 → 1.0 - 0.5 = 0.5
    assert bm.response_quality_score == pytest.approx(0.5)


# --- Outlier flagging ---

def test_outlier_flagging_drop_off_rate():
    # brand_a and brand_b have low drop-off; brand_c has very high drop-off
    results = (
        [make_result(f"a{i}", "brand_a", is_drop_off=False) for i in range(10)]
        + [make_result(f"b{i}", "brand_b", is_drop_off=False) for i in range(10)]
        + [make_result(f"c{i}", "brand_c", is_drop_off=True) for i in range(10)]
    )
    report = aggregate(results)
    brand_map = {bm.widget_id: bm for bm in report.brand_metrics}

    # brand_c should be flagged as outlier for drop_off_rate
    assert "drop_off_rate" in brand_map["brand_c"].outlier_flags
    # brand_a and brand_b should NOT be flagged for drop_off_rate
    assert "drop_off_rate" not in brand_map["brand_a"].outlier_flags
    assert "drop_off_rate" not in brand_map["brand_b"].outlier_flags


def test_no_outlier_flagging_for_single_brand():
    results = [make_result(f"c{i}", "brand_a", is_drop_off=True) for i in range(5)]
    report = aggregate(results)
    # Only 1 brand → no outlier detection
    assert report.brand_metrics[0].outlier_flags == []


# --- Systemic issue classification ---

def test_systemic_issue_present_in_majority_of_brands():
    # 4 brands all have high drop-off (> 0.3) → systemic
    results = []
    for brand in ["b1", "b2", "b3", "b4"]:
        # 8 drop-offs out of 10 → 0.8 drop-off rate
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=True) for i in range(8)]
        results += [make_result(f"{brand}_{i}_ok", brand, is_drop_off=False) for i in range(2)]

    report = aggregate(results)
    assert "high_drop_off" in report.systemic_issues


def test_systemic_issue_not_classified_when_below_50_percent():
    # Only 1 out of 4 brands has high drop-off → not systemic
    results = []
    # brand_a: 80% drop-off
    results += [make_result(f"a{i}", "brand_a", is_drop_off=True) for i in range(8)]
    results += [make_result(f"a{i}_ok", "brand_a", is_drop_off=False) for i in range(2)]
    # brands b, c, d: 0% drop-off
    for brand in ["brand_b", "brand_c", "brand_d"]:
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=False) for i in range(10)]

    report = aggregate(results)
    assert "high_drop_off" not in report.systemic_issues


# --- Brand-specific issue classification ---

def test_brand_specific_issue_present_in_minority_of_brands():
    # 10 brands, only 1 has high drop-off → brand-specific (1/10 = 10% < 20%)
    results = []
    # brand_0: 80% drop-off
    results += [make_result(f"b0_{i}", "brand_0", is_drop_off=True) for i in range(8)]
    results += [make_result(f"b0_{i}_ok", "brand_0", is_drop_off=False) for i in range(2)]
    # brands 1-9: 0% drop-off
    for idx in range(1, 10):
        brand = f"brand_{idx}"
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=False) for i in range(10)]

    report = aggregate(results)
    assert "brand_0" in report.brand_specific_issues
    assert "high_drop_off" in report.brand_specific_issues["brand_0"]


def test_brand_specific_issue_not_classified_when_above_20_percent():
    # 4 brands, 2 have high drop-off → 50% → not brand-specific
    results = []
    for brand in ["b1", "b2"]:
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=True) for i in range(8)]
        results += [make_result(f"{brand}_{i}_ok", brand, is_drop_off=False) for i in range(2)]
    for brand in ["b3", "b4"]:
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=False) for i in range(10)]

    report = aggregate(results)
    # high_drop_off is in 2/4 = 50% of brands → not brand-specific
    for issues in report.brand_specific_issues.values():
        assert "high_drop_off" not in issues


# --- Low-engagement alert ---

def test_low_engagement_alert_below_10_percent():
    # brand with 5% product engagement rate → "low_product_engagement" issue
    results = [make_result(f"c{i}", "brand_a", product_engagement=(i == 0)) for i in range(20)]
    report = aggregate(results)
    bm = report.brand_metrics[0]
    assert bm.product_engagement_rate < 0.1

    # Check the issue appears in brand_issues (systemic or brand-specific)
    all_issues = set(report.systemic_issues)
    for issues in report.brand_specific_issues.values():
        all_issues.update(issues)

    # With only 1 brand, neither systemic nor brand-specific applies (need >= 2 brands for ratios)
    # But we can verify via brand_metrics that the rate is below threshold
    # For a single brand, issue classification still runs
    # Let's verify with 2 brands where only 1 has low engagement
    results2 = (
        [make_result(f"a{i}", "brand_a", product_engagement=(i == 0)) for i in range(20)]
        + [make_result(f"b{i}", "brand_b", product_engagement=True) for i in range(20)]
    )
    report2 = aggregate(results2)
    brand_map = {bm.widget_id: bm for bm in report2.brand_metrics}
    assert brand_map["brand_a"].product_engagement_rate < 0.1
    # brand_a has low_product_engagement, brand_b does not → 1/2 = 50% → not systemic, not brand-specific
    # But the issue is still detected; verify it's in brand_issues dict
    # 1/2 = 50% → not < 20%, so not brand-specific; not > 50%, so not systemic
    # The issue exists but falls in the middle range — verify it's not incorrectly classified
    assert "low_product_engagement" not in report2.systemic_issues


def test_low_engagement_brand_specific_with_many_brands():
    # 10 brands, only 1 has low product engagement → brand-specific
    results = []
    results += [make_result(f"a{i}", "brand_a", product_engagement=False) for i in range(10)]
    for idx in range(1, 10):
        brand = f"brand_{idx}"
        results += [make_result(f"{brand}_{i}", brand, product_engagement=True) for i in range(10)]

    report = aggregate(results)
    assert "brand_a" in report.brand_specific_issues
    assert "low_product_engagement" in report.brand_specific_issues["brand_a"]


# --- Summary ---

def test_summary_total_conversations_and_brands():
    results = (
        [make_result(f"a{i}", "brand_a") for i in range(5)]
        + [make_result(f"b{i}", "brand_b") for i in range(3)]
    )
    report = aggregate(results)
    assert report.summary.total_conversations == 8
    assert report.summary.total_brands == 2


def test_summary_overall_drop_off_rate():
    results = (
        [make_result(f"a{i}", "brand_a", is_drop_off=True) for i in range(3)]
        + [make_result(f"b{i}", "brand_b", is_drop_off=False) for i in range(7)]
    )
    report = aggregate(results)
    assert report.summary.overall_drop_off_rate == pytest.approx(0.3)


def test_summary_top_3_issues():
    # Create scenario where multiple issues exist across brands
    results = []
    # 5 brands all with high drop-off and high frustration
    for idx in range(5):
        brand = f"brand_{idx}"
        results += [make_result(f"{brand}_{i}", brand, is_drop_off=True, frustration_score=0.9) for i in range(10)]

    report = aggregate(results)
    assert "high_drop_off" in report.summary.top_3_issues
    assert "high_frustration" in report.summary.top_3_issues
    assert len(report.summary.top_3_issues) <= 3


# --- Flagged conversations ---

def test_flagged_conversations_drop_off():
    results = [
        make_result("c1", "brand_a", is_drop_off=True),
        make_result("c2", "brand_a", is_drop_off=False),
    ]
    report = aggregate(results)
    flagged_ids = {fc.conversation_id for fc in report.flagged_conversations}
    assert "c1" in flagged_ids
    assert "c2" not in flagged_ids


def test_flagged_conversations_high_frustration():
    results = [
        make_result("c1", "brand_a", frustration_score=0.8),
        make_result("c2", "brand_a", frustration_score=0.3),
    ]
    report = aggregate(results)
    flagged_ids = {fc.conversation_id for fc in report.flagged_conversations}
    assert "c1" in flagged_ids
    assert "c2" not in flagged_ids


def test_flagged_conversations_flagged_responses():
    results = [
        make_result("c1", "brand_a", flagged_responses=[make_flag()]),
        make_result("c2", "brand_a"),
    ]
    report = aggregate(results)
    flagged_ids = {fc.conversation_id for fc in report.flagged_conversations}
    assert "c1" in flagged_ids
    assert "c2" not in flagged_ids
