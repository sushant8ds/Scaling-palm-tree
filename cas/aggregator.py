"""Metric aggregation for the Conversation Analysis System."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from cas.models import (
    AggregatedReport,
    AnalysisResult,
    BrandMetrics,
    ConversationPattern,
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

    # --- Hallucination summary ---
    hallucination_convs = [
        fc for fc in flagged_conversations
        if any(fr.flag_type == "hallucination" for fr in fc.flagged_responses)
    ]
    if hallucination_convs:
        hallucination_brands = list({fc.widget_id for fc in hallucination_convs})
        total_hallucinations = sum(
            1 for fc in hallucination_convs
            for fr in fc.flagged_responses if fr.flag_type == "hallucination"
        )
        insights.append(Insight(
            title="Assistant making unverifiable specific claims (potential hallucination)",
            description=(
                f"{total_hallucinations} agent responses across {len(hallucination_convs)} conversations "
                f"contain specific claims about prices, delivery timelines, offer details, or efficacy "
                f"that cannot be verified against a product catalog. "
                f"Affects {len(hallucination_brands)} brand(s). "
                "If these claims are incorrect, users are being misled — this is a trust risk."
            ),
            severity="HIGH" if len(hallucination_convs) > 5 else "MEDIUM",
            recommendation=(
                "Integrate the assistant with a live product catalog API so claims can be verified at response time. "
                "Add guardrails to prevent the assistant from stating specific prices, delivery dates, or offer details "
                "unless retrieved from a verified source. "
                "Review flagged conversations manually to confirm which claims are incorrect."
            ),
            affected_brands=hallucination_brands,
        ))

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

    # --- Cross-brand performance comparison insight ---
    if len(brand_metrics_list) >= 2:
        sorted_by_quality = sorted(brand_metrics_list, key=lambda b: b.response_quality_score)
        worst = sorted_by_quality[0]
        best = sorted_by_quality[-1]
        quality_gap = best.response_quality_score - worst.response_quality_score

        if quality_gap > 0.1:
            insights.append(Insight(
                title="Significant performance gap between brands",
                description=(
                    f"Brand `{worst.widget_id}` has a response quality score of {worst.response_quality_score:.2f} "
                    f"while brand `{best.widget_id}` scores {best.response_quality_score:.2f} — "
                    f"a gap of {quality_gap:.2f}. "
                    f"The underperforming brand also has {worst.drop_off_rate*100:.0f}% drop-off vs "
                    f"{best.drop_off_rate*100:.0f}% for the best brand. "
                    "Possible reasons: the underperforming brand's assistant may have a poorly configured "
                    "knowledge base, an outdated product catalog, a system prompt not scoped to its domain, "
                    "or it handles a more complex query type (e.g. order issues vs simple product questions)."
                ),
                severity="HIGH" if quality_gap > 0.2 else "MEDIUM",
                recommendation=(
                    "Compare the assistant configurations across brands. "
                    "Check if the underperforming brand has: (1) an up-to-date product catalog, "
                    "(2) a system prompt that covers its specific domain, "
                    "(3) fallback handling for query types it frequently fails on. "
                    "Use the flagged conversations from the underperforming brand as a training set "
                    "to identify the specific query types causing failures."
                ),
                affected_brands=[worst.widget_id],
            ))

    # Sort by severity
    _severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    insights.sort(key=lambda i: _severity_order.get(i.severity, 3))
    return insights


def _analyze_weak_topics(results: list[AnalysisResult]) -> list[ConversationPattern]:
    """Find which topic categories have the most quality issues."""
    from collections import Counter

    topic_total: Counter = Counter()
    topic_flagged: Counter = Counter()
    topic_dropoff: Counter = Counter()

    for r in results:
        for topic in r.topic_categories:
            topic_total[topic] += 1
            if r.flagged_responses:
                topic_flagged[topic] += 1
            if r.is_drop_off:
                topic_dropoff[topic] += 1

    patterns = []
    for topic, total in topic_total.items():
        if total < 3:
            continue
        flag_rate = topic_flagged[topic] / total
        dropoff_rate = topic_dropoff[topic] / total

        if flag_rate > 0.3 or dropoff_rate > 0.15:
            patterns.append(ConversationPattern(
                pattern_name=f"Assistant struggles with '{topic}' questions",
                description=(
                    f"Conversations classified as '{topic}' have a {flag_rate*100:.0f}% quality flag rate "
                    f"and {dropoff_rate*100:.0f}% drop-off rate. "
                    f"Out of {total} conversations in this category, "
                    f"{topic_flagged[topic]} had flagged responses and {topic_dropoff[topic]} ended in drop-off."
                ),
                evidence=(
                    f"Topic '{topic}': {total} conversations, "
                    f"{topic_flagged[topic]} flagged ({flag_rate*100:.0f}%), "
                    f"{topic_dropoff[topic]} drop-offs ({dropoff_rate*100:.0f}%)"
                ),
                affected_brands=[],
                conversation_count=total,
            ))

    # Sort by flag rate descending
    patterns.sort(key=lambda p: p.conversation_count, reverse=True)
    return patterns


def _detect_patterns(
    results: list[AnalysisResult],
    flagged_conversations: list[FlaggedConversation],
    brand_metrics_list: list[BrandMetrics],
) -> list[ConversationPattern]:
    """Detect recurring patterns across conversations."""
    patterns: list[ConversationPattern] = []

    # Pattern 1: Drop-off after irrelevant response
    dropoff_after_irrelevant = [
        fc for fc in flagged_conversations
        if fc.drop_off and any(fr.flag_type == "irrelevant" for fr in fc.flagged_responses)
    ]
    if dropoff_after_irrelevant:
        brands = list({fc.widget_id for fc in dropoff_after_irrelevant})
        patterns.append(ConversationPattern(
            pattern_name="Drop-off after irrelevant response",
            description=(
                "Users are abandoning conversations after receiving agent responses "
                "that don't address their question. This suggests the assistant's failure "
                "to answer is directly causing users to give up."
            ),
            evidence=(
                f"{len(dropoff_after_irrelevant)} conversations ended with a user drop-off "
                f"AND had at least one irrelevant agent response. "
                f"This pattern appears in {len(brands)} brand(s)."
            ),
            affected_brands=brands,
            conversation_count=len(dropoff_after_irrelevant),
        ))

    # Pattern 2: Frustration without drop-off (persistent frustrated users)
    frustrated_no_dropoff = [
        fc for fc in flagged_conversations
        if fc.frustration_score > 0.5 and not fc.drop_off
    ]
    if frustrated_no_dropoff:
        brands = list({fc.widget_id for fc in frustrated_no_dropoff})
        patterns.append(ConversationPattern(
            pattern_name="Frustrated users who stayed in conversation",
            description=(
                "Users expressed frustration but continued the conversation rather than leaving. "
                "These are high-value recovery opportunities — the user is still engaged "
                "but the assistant is not resolving their issue."
            ),
            evidence=(
                f"{len(frustrated_no_dropoff)} conversations had frustration scores above 0.5 "
                f"but the user did not drop off. Appears in {len(brands)} brand(s)."
            ),
            affected_brands=brands,
            conversation_count=len(frustrated_no_dropoff),
        ))

    # Pattern 3: Multiple irrelevant responses in same conversation
    multi_irrelevant = [
        fc for fc in flagged_conversations
        if sum(1 for fr in fc.flagged_responses if fr.flag_type == "irrelevant") >= 3
    ]
    if multi_irrelevant:
        brands = list({fc.widget_id for fc in multi_irrelevant})
        patterns.append(ConversationPattern(
            pattern_name="Repeated irrelevant responses in single conversation",
            description=(
                "Some conversations have 3 or more irrelevant agent responses in a row. "
                "This indicates the assistant is stuck in a loop — unable to understand "
                "the user's intent across multiple turns."
            ),
            evidence=(
                f"{len(multi_irrelevant)} conversations had 3+ irrelevant responses. "
                f"Appears in {len(brands)} brand(s). "
                f"Worst case: {max(sum(1 for fr in fc.flagged_responses if fr.flag_type == 'irrelevant') for fc in multi_irrelevant)} irrelevant responses in one conversation."
            ),
            affected_brands=brands,
            conversation_count=len(multi_irrelevant),
        ))

    # Pattern 4: High frustration + hallucination (dangerous combination)
    frustrated_hallucination = [
        fc for fc in flagged_conversations
        if fc.frustration_score > 0.5 and any(fr.flag_type == "hallucination" for fr in fc.flagged_responses)
    ]
    if frustrated_hallucination:
        brands = list({fc.widget_id for fc in frustrated_hallucination})
        patterns.append(ConversationPattern(
            pattern_name="Frustrated users receiving unverifiable claims",
            description=(
                "Already-frustrated users are receiving agent responses with unverifiable "
                "specific claims (prices, delivery dates, availability). This is the highest-risk "
                "pattern — a frustrated user who receives wrong information is likely to escalate."
            ),
            evidence=(
                f"{len(frustrated_hallucination)} conversations had both high frustration "
                f"AND potential hallucinations. Appears in {len(brands)} brand(s)."
            ),
            affected_brands=brands,
            conversation_count=len(frustrated_hallucination),
        ))

    return patterns + _analyze_weak_topics(results)


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
            patterns=[],
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
    # For small datasets (< 5 brands), use absolute count instead of percentage
    # Brand-specific = only 1 brand has the issue
    brand_specific_issues: dict[str, list[str]] = {
        widget_id: [
            issue for issue in issues
            if issue_brand_count[issue] == 1
        ]
        for widget_id, issues in brand_issues.items()
        if any(issue_brand_count[issue] == 1 for issue in issues)
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
        patterns=_detect_patterns(results, flagged_conversations, brand_metrics_list),
    )
