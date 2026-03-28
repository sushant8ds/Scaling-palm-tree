"""Tests for the drop-off and frustration analyzer."""

from __future__ import annotations

from datetime import datetime

import pytest

from cas.analyzers.dropoff import analyze
from cas.models import Conversation, EnrichedConversation, Message


def _conv(messages: list[Message]) -> EnrichedConversation:
    conv = Conversation(
        id="c1",
        widget_id="brand_a",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )
    return EnrichedConversation(conversation=conv, messages=messages)


def _msg(sender: str, text: str, message_type: str = "text", idx: int = 0) -> Message:
    return Message(
        id=f"m{idx}",
        conversation_id="c1",
        sender=sender,
        message_type=message_type,
        text=text,
        timestamp=datetime(2024, 1, 1, 0, idx),
    )


# --- Drop-off detection ---

def test_drop_off_when_last_message_is_user():
    msgs = [
        _msg("user", "Hello", idx=0),
        _msg("agent", "Hi there!", idx=1),
        _msg("user", "Still waiting for help", idx=2),
    ]
    result = analyze(_conv(msgs))
    assert result["is_drop_off"] is True


def test_no_drop_off_when_last_message_is_agent():
    msgs = [
        _msg("user", "Hello", idx=0),
        _msg("agent", "How can I help you?", idx=1),
    ]
    result = analyze(_conv(msgs))
    assert result["is_drop_off"] is False


def test_no_drop_off_when_only_agent_messages():
    msgs = [
        _msg("agent", "Welcome!", idx=0),
        _msg("agent", "Let me know if you need help.", idx=1),
    ]
    result = analyze(_conv(msgs))
    assert result["is_drop_off"] is False


def test_no_drop_off_when_no_text_messages():
    msgs = [
        _msg("user", "", message_type="event", idx=0),
    ]
    result = analyze(_conv(msgs))
    assert result["is_drop_off"] is False


# --- Frustration scoring ---

def test_frustration_score_with_negative_keywords():
    msgs = [
        _msg("user", "This is terrible and awful service", idx=0),
        _msg("agent", "I'm sorry to hear that.", idx=1),
    ]
    result = analyze(_conv(msgs))
    assert result["frustration_score"] > 0.0


def test_frustration_score_with_confusion_phrases():
    msgs = [
        _msg("user", "I don't understand, this doesn't make sense", idx=0),
        _msg("agent", "Let me clarify.", idx=1),
    ]
    result = analyze(_conv(msgs))
    assert result["frustration_score"] > 0.0


def test_frustration_score_with_repeated_questions():
    msgs = [
        _msg("user", "Where is my order status update?", idx=0),
        _msg("agent", "Let me check.", idx=1),
        _msg("user", "Where is my order status?", idx=2),
        _msg("agent", "Still checking.", idx=3),
    ]
    result = analyze(_conv(msgs))
    assert result["frustration_score"] > 0.0


def test_neutral_conversation_has_low_frustration():
    msgs = [
        _msg("user", "Can you show me some blue shoes?", idx=0),
        _msg("agent", "Sure, here are some options.", idx=1),
        _msg("user", "Thanks, I like the second one.", idx=2),
        _msg("agent", "Great choice!", idx=3),
    ]
    result = analyze(_conv(msgs))
    assert result["frustration_score"] == 0.0


def test_frustration_score_always_in_range():
    # Maximally frustrated conversation
    msgs = [
        _msg("user", "This is terrible, awful, horrible, disgusting, pathetic waste", idx=0),
        _msg("user", "I don't understand, this doesn't make sense, not helpful", idx=1),
        _msg("user", "This is terrible waste of time, still not working", idx=2),
        _msg("user", "Terrible waste still not working, not helpful at all", idx=3),
    ]
    result = analyze(_conv(msgs))
    score = result["frustration_score"]
    assert 0.0 <= score <= 1.0


def test_frustration_score_empty_conversation():
    result = analyze(_conv([]))
    assert result["frustration_score"] == 0.0
    assert result["is_drop_off"] is False


def test_frustration_only_counts_user_text_messages():
    # Agent messages with negative words should not affect score
    msgs = [
        _msg("agent", "This is terrible and awful", idx=0),
        _msg("user", "Thank you for your help", idx=1),
        _msg("agent", "You're welcome", idx=2),
    ]
    result = analyze(_conv(msgs))
    assert result["frustration_score"] == 0.0
