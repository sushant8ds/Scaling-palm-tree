"""Tests for the response quality analyzer."""

from __future__ import annotations

from datetime import datetime

import pytest

from cas.analyzers.quality import analyze
from cas.models import Conversation, EnrichedConversation, Message


def _conv(messages: list[Message]) -> EnrichedConversation:
    return EnrichedConversation(
        conversation=Conversation(
            id="conv-1",
            widget_id="brand-1",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
        ),
        messages=messages,
    )


def _msg(id: str, sender: str, text: str, message_type: str = "text") -> Message:
    return Message(
        id=id,
        conversation_id="conv-1",
        sender=sender,
        message_type=message_type,
        text=text,
        timestamp=datetime(2024, 1, 1),
    )


# --- Verbose tests ---

def test_verbose_flag_when_over_500_words():
    long_text = " ".join(["word"] * 501)
    conv = _conv([
        _msg("u1", "user", "Hello"),
        _msg("a1", "agent", long_text),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "verbose"]
    assert len(flags) == 1
    assert flags[0].message_id == "a1"
    assert flags[0].confidence == 1.0
    assert flags[0].reason == "Response exceeds 500 words"


def test_no_verbose_flag_at_exactly_500_words():
    text_500 = " ".join(["word"] * 500)
    conv = _conv([
        _msg("u1", "user", "Hello"),
        _msg("a1", "agent", text_500),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "verbose"]
    assert len(flags) == 0


# --- Irrelevant tests ---

def test_irrelevant_flag_when_zero_keyword_overlap():
    conv = _conv([
        _msg("u1", "user", "What is the return policy for shoes?"),
        _msg("a1", "agent", "Bananas are yellow tropical fruit."),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "irrelevant"]
    assert len(flags) == 1
    assert flags[0].message_id == "a1"
    assert flags[0].confidence == 0.7


def test_no_irrelevant_flag_when_keyword_overlap_exists():
    conv = _conv([
        _msg("u1", "user", "What is the return policy for shoes?"),
        _msg("a1", "agent", "Our return policy allows you to return shoes within 30 days."),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "irrelevant"]
    assert len(flags) == 0


def test_no_irrelevant_flag_for_first_agent_message_with_no_preceding_user_message():
    conv = _conv([
        _msg("a1", "agent", "Welcome! How can I help you today?"),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "irrelevant"]
    assert len(flags) == 0


# --- Hallucination tests ---

def test_hallucination_flag_with_two_or_more_numeric_patterns():
    text = "This product costs $49.99 and ships in 3 days."
    conv = _conv([
        _msg("u1", "user", "Tell me about this product."),
        _msg("a1", "agent", text),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "hallucination"]
    assert len(flags) == 1
    assert flags[0].message_id == "a1"


def test_no_hallucination_flag_with_only_one_numeric_pattern():
    text = "This product costs $49.99 and it is great."
    conv = _conv([
        _msg("u1", "user", "Tell me about this product."),
        _msg("a1", "agent", text),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "hallucination"]
    assert len(flags) == 0


def test_hallucination_flagged_response_fields():
    text = "The price is $99.99 and it ships in 5 days."
    conv = _conv([
        _msg("u1", "user", "How much does it cost?"),
        _msg("a1", "agent", text),
    ])
    result = analyze(conv)
    flags = [f for f in result["flagged_responses"] if f.flag_type == "hallucination"]
    assert len(flags) == 1
    flag = flags[0]
    assert flag.message_id  # non-empty
    assert 0.0 <= flag.confidence <= 1.0
    assert flag.reason  # non-empty


# --- Multiple flags on same message ---

def test_message_can_have_multiple_flags():
    long_irrelevant = " ".join(["banana"] * 501)
    conv = _conv([
        _msg("u1", "user", "What is the return policy for shoes?"),
        _msg("a1", "agent", long_irrelevant),
    ])
    result = analyze(conv)
    flag_types = {f.flag_type for f in result["flagged_responses"] if f.message_id == "a1"}
    assert "verbose" in flag_types
    assert "irrelevant" in flag_types
