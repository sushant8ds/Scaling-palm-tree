"""Metric aggregation for the Conversation Analysis System."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from cas.models import (
    AggregatedReport,
    AnalysisResult,
    BrandMetrics,
    FlaggedConversation,
    Insight,
    ReportSummary,
)

_METRICS = ("drop_off_rate", "frustration_rate", "response_quality_score", "product_engagement_rate")

_ISSUE_THRESHOLDS = {
    "high_drop_off": lambda m: m.drop_off_rate > 0.3,
    "high_frustration": lambda m: m.frustration_rate > 0.2,
    "low_response_quality": lambda m: m.response_quality_score < 0.7,
    "low_product_engagement": lambda m: m.product_engagement_rate < 0.1,
}


def _mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _generate_insights(
    brand_metrics_list: list[BrandMetrics],
    flagged_conversations: list[FlaggedConversation],
) -> list[Insight]:
    insights: list[Insight] = []

    # --- Irrelevant responses ---
    irrelevant_brands = [
        bm.widget_id for bm in brand_metrics_list
        if bm.response_quality_score < 0.5
    ]
    all_irrelevant_count = sum(
        1 for fc in flagged_conversations
        for fr in fc.flagged_responses
        if fr.flag_type == "irrelevant"
    )
    if all_irrelevant_count > 0:
        severity = "HIGH" if irrelevant_brands else "MEDIUM"
        insights.append(Insight(
            title="Irrelevant agent responses detected",
            description=(
                f"{all_irrelevant_count} agent responses were flagged as irrelevant — "
                "the assistant replied without addressing the user's actual question. "
                f"{'Brands with critically low quality: ' + ', '.join(irrelevant_brands) + '.' if irrelevant_brands else 'Affects all brands to varying degrees.'}"
            ),
            severity=severity,
            recommendation=(
                "Improve intent detection before response generation. "
                "Add a retrieval step that matches user queries to relevant product/policy content "
                "before the assistant formulates a reply."
            ),
            affected_brands=irrelevant_brands or [bm.widget_id for bm in brand_metrics_list],
        ))

    # --- Verbose responses ---
    verbose_brands = []
    verbose_count = 0
    for fc in flagged_conversations:
        brand_verbose = [fr for fr in fc.flagged_responses if fr.flag_type == "verbose"]
        if brand_verbose:
            verbose_count += len(brand_verbose)
            if fc.widget_id not in verbose_brands:
                verbose_brands.append(fc.widget_id)
    if verbose_count > 0:
        insights.append(Insight(
            title="Over-verbose responses reducing user experience",
            description=(
                f"{verbose_count} agent responses exceeded 500 words. "
                "Long responses increase cognitive load and are associated with user drop-off."
            ),
            severity="MEDIUM",
            recommendation=(
                "Set a hard response length limit in the assistant configuration (recommended: 150–250 words). "
                "Use bullet points and structured formatting for complex answers instead of long paragraphs."
            ),
            affected_brands=list(set(verbose_brands)),
        ))

    # --- Drop-off ---
    high_dropoff_brands = [
        bm for bm in brand_metrics_list if bm.drop_off_rate > 0.1
    ]
    if high_dropoff_brands:
        worst = max(high_dropoff_brands, key=lambda b: b.drop_off_rate)
        insights.append(Insight(
            title="High conversation drop-off rate",
            description=(
                f"{len(high_dropoff_brands)} brand(s) have drop-off rates above 10%. "
                f"Brand {worst.widget_id} is worst at {worst.drop_off_rate * 100:.1f}% — "
                "users are abandoning conversations without resolution."
            ),
            severity="HIGH" if worst.drop_off_rate > 0.2 else "MEDIUM",
            recommendation=(
                "Analyze the last user message in dropped conversations to identify unhandled intents. "
                "Add fallback responses and proactive re-engagement prompts when the assistant cannot answer."
            ),
            affected_brands=[bm.widget_id for bm in high_dropoff_brands],
        ))

    # --- Low product engagement ---
    low_engagement_brands = [
        bm for bm in brand_metrics_list if bm.product_engagement_rate < 0.1
    ]
    if low_engagement_brands:
        insights.append(Insight(
            title="Product suggestions not driving engagement",
            description=(
                f"{len(low_engagement_brands)} brand(s) have product engagement rates below 10%. "
                "Users are not clicking on suggested products, indicating recommendations may be irrelevant or poorly presented."
            ),
            severity="HIGH" if any(bm.product_engagement_rate < 0.05 for bm in low_engagement_brands) else "MEDIUM",
            recommendation=(
                "Review product recommendation logic — ensure suggestions are contextually matched to the user's query. "
                "Consider adding personalisation signals (e.g. price range, category preference) and "
                "improving how products are presented in the chat (images, concise descriptions, direct links)."
            ),
            affected_brands=[bm.widget_id for bm in low_engagement_brands],
        ))

    # --- Response quality outlier ---
    quality_outliers = [
        bm for bm in brand_metrics_list
        if "response_quality_score" in bm.outlier_flags and bm.response_quality_score < 0.6
    ]
    if quality_outliers:
        worst_q = min(quality_outliers, key=lambda b: b.response_quality_score)
        insights.append(Insight(
            title="Response quality significantly below average",
            description=(
                f"Brand {worst_q.widget_id} has a response quality score of {worst_q.response_quality_score:.2f}, "
                "which is a statistical outlier below the cross-brand average. "
                "This brand's assistant is producing disproportionately more flagged responses."
            ),
            severity="HIGH",
            recommendation=(
                "Audit the knowledge base and prompt configuration for this brand specifically. "
                "Check if the product catalog is up to date and if the assistant's system prompt "
                "is correctly scoped to the brand's domain."
            ),
            affected_brands=[worst_q.widget_id],
        ))

    # Sort by severity
    _severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    insights.sort(key=lambda i: _severity_order.get(i.severity, 3))
    return insights


def aggregate(
    results: list[AnalysisResult],
    filters_applied: dict | None = None,
) -> AggregatedReport:
    if filters_applied is None:
        filters_applied = {}

    run_date = datetime.now(tz=timezone.utc)

    if not results:
        return AggregatedReport(
            run_date=run_date,
            filters_applied=filters_applied,
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
            insights=[],
        )

    # 1. Group by widget_id
    grouped: dict[str, list[AnalysisResult]] = defaultdict(list)
    for r in results:
        grouped[r.widget_id].append(r)

    # 2. Per-brand metrics
    brand_metrics_list: list[BrandMetrics] = []
    for widget_id, brand_results in grouped.items():
        total = len(brand_results)
        drop_off_count = sum(1 for r in brand_results if r.is_drop_off)
        frustration_count = sum(1 for r in brand_results if r.frustration_score > 0.5)
        flagged_count = sum(1 for r in brand_results if len(r.flagged_responses) > 0)
        engagement_count = sum(1 for r in brand_results if r.product_engagement)

        drop_off_rate = drop_off_count / total
        frustration_rate = frustration_count / total
        response_quality_score = max(0.0, min(1.0, 1.0 - (flagged_count / total)))
        product_engagement_rate = engagement_count / total

        brand_metrics_list.append(
            BrandMetrics(
                widget_id=widget_id,
                total_conversations=total,
                drop_off_rate=drop_off_rate,
                frustration_rate=frustration_rate,
                response_quality_score=response_quality_score,
                product_engagement_rate=product_engagement_rate,
                outlier_flags=[],
            )
        )

    # 3. Outlier detection (only if >= 2 brands)
    if len(brand_metrics_list) >= 2:
        for metric in _METRICS:
            values = [getattr(m, metric) for m in brand_metrics_list]
            mean, std = _mean_std(values)
            for bm in brand_metrics_list:
                if abs(getattr(bm, metric) - mean) > std:
                    bm.outlier_flags.append(metric)

    # 4. Issue classification
    brand_issues: dict[str, list[str]] = {}
    for bm in brand_metrics_list:
        issues = [name for name, check in _ISSUE_THRESHOLDS.items() if check(bm)]
        brand_issues[bm.widget_id] = issues

    total_brands = len(brand_metrics_list)
    # Count how many brands have each issue
    issue_brand_count: dict[str, int] = defaultdict(int)
    for issues in brand_issues.values():
        for issue in issues:
            issue_brand_count[issue] += 1

    systemic_issues = [
        issue for issue, count in issue_brand_count.items()
        if count / total_brands > 0.5
    ]
    brand_specific_issues: dict[str, list[str]] = {
        widget_id: [
            issue for issue in issues
            if issue_brand_count[issue] / total_brands < 0.2
        ]
        for widget_id, issues in brand_issues.items()
        if any(issue_brand_count[issue] / total_brands < 0.2 for issue in issues)
    }

    # 5. Flagged conversations
    flagged_conversations: list[FlaggedConversation] = []
    for r in results:
        reasons = []
        if r.is_drop_off:
            reasons.append("drop_off")
        if r.frustration_score > 0.5:
            reasons.append("high_frustration")
        if len(r.flagged_responses) > 0:
            reasons.append("flagged_responses")

        if reasons:
            flagged_conversations.append(
                FlaggedConversation(
                    conversation_id=r.conversation_id,
                    widget_id=r.widget_id,
                    flag_reason=", ".join(reasons),
                    drop_off=r.is_drop_off,
                    frustration_score=r.frustration_score,
                    flagged_responses=r.flagged_responses,
                )
            )

    # 6. Summary
    total_conversations = len(results)
    overall_drop_off_rate = sum(1 for r in results if r.is_drop_off) / total_conversations

    top_3_issues = sorted(issue_brand_count, key=lambda i: issue_brand_count[i], reverse=True)[:3]

    summary = ReportSummary(
        total_conversations=total_conversations,
        total_brands=total_brands,
        overall_drop_off_rate=overall_drop_off_rate,
        top_3_issues=top_3_issues,
    )

    return AggregatedReport(
        run_date=run_date,
        filters_applied=filters_applied,
        brand_metrics=brand_metrics_list,
        flagged_conversations=flagged_conversations,
        systemic_issues=systemic_issues,
        brand_specific_issues=brand_specific_issues,
        summary=summary,
        insights=_generate_insights(brand_metrics_list, flagged_conversations),
    )
