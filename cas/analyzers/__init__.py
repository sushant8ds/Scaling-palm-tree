"""Conversation analysis pipeline.

Wires all individual analyzers into a single `analyze` entry point.
"""

from __future__ import annotations

from cas.models import AnalysisResult, EnrichedConversation, FlaggedResponse
from cas.analyzers import segmentation, dropoff, quality, products


def analyze(conv: EnrichedConversation) -> AnalysisResult:
    """Run all analyzers and merge results into a single AnalysisResult.

    Args:
        conv: An enriched conversation with metadata and messages.

    Returns:
        AnalysisResult containing all analysis fields.
    """
    seg = segmentation.analyze(conv)
    drop = dropoff.analyze(conv)
    qual = quality.analyze(conv)
    prod = products.analyze(conv)

    return AnalysisResult(
        conversation_id=conv.conversation.id,
        widget_id=conv.conversation.widget_id,
        topic_categories=seg["topic_categories"],
        is_unanswered=seg["is_unanswered"],
        is_drop_off=drop["is_drop_off"],
        frustration_score=drop["frustration_score"],
        flagged_responses=qual["flagged_responses"],
        product_engagement=prod["product_engagement"],
        low_engagement_product_rec=prod["low_engagement_product_rec"],
    )


__all__ = ["analyze", "AnalysisResult", "FlaggedResponse"]
