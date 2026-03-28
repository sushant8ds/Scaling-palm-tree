"""Integration test for the full analyzers pipeline."""

from __future__ import annotations

from datetime import datetime

import cas.analyzers as analyzers
from cas.models import (
    AnalysisResult,
    Conversation,
    EnrichedConversation,
    FlaggedResponse,
    Message,
)


def _make_conv() -> EnrichedConversation:
    conversation = Conversation(
        id="conv-integration-1",
        widget_id="brand-x",
        created_at=datetime(2024, 6, 1),
        updated_at=datetime(2024, 6, 1),
    )
    messages = [
        Message(
            id="m1",
            conversation_id="conv-integration-1",
            sender="user",
            message_type="text",
            text="I'm looking for a blue jacket, what do you recommend?",
            timestamp=datetime(2024, 6, 1, 10, 0),
        ),
        Message(
            id="m2",
            conversation_id="conv-integration-1",
            sender="agent",
            message_type="text",
            text="Here are some great options for you — check out our new arrivals.",
            timestamp=datetime(2024, 6, 1, 10, 1),
        ),
        Message(
            id="m3",
            conversation_id="conv-integration-1",
            sender="user",
            message_type="event",
            text="",
            timestamp=datetime(2024, 6, 1, 10, 2),
            metadata={"eventType": "product_view"},
        ),
        Message(
            id="m4",
            conversation_id="conv-integration-1",
            sender="user",
            message_type="text",
            text="Thanks, I like the first one.",
            timestamp=datetime(2024, 6, 1, 10, 3),
        ),
    ]
    return EnrichedConversation(conversation=conversation, messages=messages)


def test_pipeline_returns_analysis_result():
    conv = _make_conv()
    result = analyzers.analyze(conv)
    assert isinstance(result, AnalysisResult)


def test_pipeline_result_field_types():
    conv = _make_conv()
    result = analyzers.analyze(conv)

    assert isinstance(result.conversation_id, str)
    assert isinstance(result.widget_id, str)
    assert isinstance(result.topic_categories, list)
    assert all(isinstance(c, str) for c in result.topic_categories)
    assert isinstance(result.is_unanswered, bool)
    assert isinstance(result.is_drop_off, bool)
    assert isinstance(result.frustration_score, float)
    assert isinstance(result.flagged_responses, list)
    assert all(isinstance(f, FlaggedResponse) for f in result.flagged_responses)
    assert isinstance(result.product_engagement, bool)
    assert isinstance(result.low_engagement_product_rec, bool)


def test_pipeline_correct_values_for_mixed_conversation():
    conv = _make_conv()
    result = analyzers.analyze(conv)

    # IDs propagated correctly
    assert result.conversation_id == "conv-integration-1"
    assert result.widget_id == "brand-x"

    # Agent replied → not unanswered; last text message is user → drop-off
    assert result.is_unanswered is False
    assert result.is_drop_off is True

    # product_view event present → product_engagement True
    assert result.product_engagement is True

    # Agent suggested products AND there was engagement → not low engagement
    assert result.low_engagement_product_rec is False

    # Frustration score in valid range
    assert 0.0 <= result.frustration_score <= 1.0
