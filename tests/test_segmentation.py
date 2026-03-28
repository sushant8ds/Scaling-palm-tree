"""Unit tests for cas/analyzers/segmentation.py"""

from __future__ import annotations

from datetime import datetime

import pytest

from cas.analyzers.segmentation import analyze
from cas.models import Conversation, EnrichedConversation, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conv(messages: list[Message]) -> EnrichedConversation:
    conversation = Conversation(
        id="conv-1",
        widget_id="brand-1",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )
    return EnrichedConversation(conversation=conversation, messages=messages)


def _msg(
    sender: str,
    text: str,
    message_type: str = "text",
    msg_id: str = "m1",
) -> Message:
    return Message(
        id=msg_id,
        conversation_id="conv-1",
        sender=sender,
        message_type=message_type,
        text=text,
        timestamp=datetime(2024, 1, 1, 12, 0),
    )


# ---------------------------------------------------------------------------
# Topic classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,expected_category", [
    ("what is the color of this item?", "product_question"),
    ("how does this work?", "product_question"),
    ("tell me about the features", "product_question"),
    ("what are the specs?", "product_question"),
    ("my order hasn't arrived", "order_issue"),
    ("I want to return this", "order_issue"),
    ("track my delivery", "order_issue"),
    ("I got a damaged item", "order_issue"),
    ("can you recommend something?", "recommendation_request"),
    ("which one is best?", "recommendation_request"),
    ("I'm looking for a gift", "recommendation_request"),
    ("help me find something similar", "recommendation_request"),
    ("what is your return policy?", "policy_inquiry"),
    ("does it come with a warranty?", "policy_inquiry"),
    ("what are the terms and conditions?", "policy_inquiry"),
])
def test_known_phrases_map_to_expected_category(phrase: str, expected_category: str) -> None:
    conv = _conv([_msg("user", phrase)])
    result = analyze(conv)
    assert expected_category in result["topic_categories"], (
        f"Expected '{expected_category}' for phrase: {phrase!r}, "
        f"got: {result['topic_categories']}"
    )


# ---------------------------------------------------------------------------
# Unanswered detection
# ---------------------------------------------------------------------------

def test_single_user_message_is_unanswered() -> None:
    conv = _conv([_msg("user", "hello, I need help")])
    result = analyze(conv)
    assert result["is_unanswered"] is True


def test_conversation_with_agent_reply_is_not_unanswered() -> None:
    conv = _conv([
        _msg("user", "what is the return policy?", msg_id="m1"),
        _msg("agent", "Our return policy is 30 days.", msg_id="m2"),
    ])
    result = analyze(conv)
    assert result["is_unanswered"] is False


def test_event_only_conversation_is_unanswered() -> None:
    """A conversation with only event messages has no agent reply → unanswered."""
    conv = _conv([
        _msg("user", "", message_type="event", msg_id="m1"),
    ])
    result = analyze(conv)
    assert result["is_unanswered"] is True


# ---------------------------------------------------------------------------
# Event-only conversation topic categories
# ---------------------------------------------------------------------------

def test_event_only_conversation_topic_categories() -> None:
    """Event messages are not used for topic classification; fallback to 'general'."""
    conv = _conv([
        _msg("user", "product_view", message_type="event", msg_id="m1"),
    ])
    result = analyze(conv)
    # No user text messages → should fall back to "general" or be empty-ish
    assert result["topic_categories"] == ["general"] or result["topic_categories"] == []


# ---------------------------------------------------------------------------
# Multiple topic categories
# ---------------------------------------------------------------------------

def test_multiple_topic_categories_detected() -> None:
    """A conversation with messages matching different categories gets multiple categories."""
    conv = _conv([
        _msg("user", "what are the specs of this product?", msg_id="m1"),
        _msg("agent", "Here are the specs.", msg_id="m2"),
        _msg("user", "also, I want to return my order", msg_id="m3"),
    ])
    result = analyze(conv)
    categories = result["topic_categories"]
    assert "product_question" in categories
    assert "order_issue" in categories


def test_topic_categories_are_deduplicated() -> None:
    """Same category matched by multiple messages should appear only once."""
    conv = _conv([
        _msg("user", "what is the color?", msg_id="m1"),
        _msg("user", "what is the size?", msg_id="m2"),
    ])
    result = analyze(conv)
    categories = result["topic_categories"]
    assert categories.count("product_question") == 1


# ---------------------------------------------------------------------------
# Fallback to "general"
# ---------------------------------------------------------------------------

def test_unrecognized_message_falls_back_to_general() -> None:
    conv = _conv([_msg("user", "okay thanks bye")])
    result = analyze(conv)
    assert result["topic_categories"] == ["general"]


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------

def test_analyze_returns_required_keys() -> None:
    conv = _conv([_msg("user", "hello")])
    result = analyze(conv)
    assert "topic_categories" in result
    assert "is_unanswered" in result
    assert isinstance(result["topic_categories"], list)
    assert isinstance(result["is_unanswered"], bool)
