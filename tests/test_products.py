"""Tests for the product suggestion analyzer."""

from __future__ import annotations

from datetime import datetime

from cas.analyzers.products import analyze
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


def _text_msg(id: str, sender: str, text: str) -> Message:
    return Message(
        id=id,
        conversation_id="conv-1",
        sender=sender,
        message_type="text",
        text=text,
        timestamp=datetime(2024, 1, 1),
    )


def _event_msg(id: str, event_type: str) -> Message:
    return Message(
        id=id,
        conversation_id="conv-1",
        sender="user",
        message_type="event",
        text="",
        timestamp=datetime(2024, 1, 1),
        metadata={"eventType": event_type},
    )


# --- product_engagement tests ---

def test_product_engagement_true_when_product_view_event_present():
    conv = _conv([
        _text_msg("u1", "user", "Show me some shoes."),
        _event_msg("e1", "product_view"),
    ])
    result = analyze(conv)
    assert result["product_engagement"] is True


def test_product_engagement_false_when_no_events():
    conv = _conv([
        _text_msg("u1", "user", "Show me some shoes."),
        _text_msg("a1", "agent", "Here are some options for you."),
    ])
    result = analyze(conv)
    assert result["product_engagement"] is False


def test_product_engagement_true_for_product_click_event():
    conv = _conv([
        _event_msg("e1", "product_click"),
    ])
    result = analyze(conv)
    assert result["product_engagement"] is True


def test_product_engagement_true_for_add_to_cart_event():
    conv = _conv([
        _event_msg("e1", "add_to_cart"),
    ])
    result = analyze(conv)
    assert result["product_engagement"] is True


def test_product_engagement_false_for_non_product_event():
    conv = _conv([
        _event_msg("e1", "quick_reply"),
    ])
    result = analyze(conv)
    assert result["product_engagement"] is False


# --- low_engagement_product_rec tests ---

def test_low_engagement_true_when_suggestion_text_but_no_engagement_events():
    conv = _conv([
        _text_msg("u1", "user", "What do you recommend?"),
        _text_msg("a1", "agent", "I recommend checking out our new arrivals."),
    ])
    result = analyze(conv)
    assert result["low_engagement_product_rec"] is True


def test_low_engagement_false_when_suggestion_text_and_engagement_events():
    conv = _conv([
        _text_msg("u1", "user", "What do you recommend?"),
        _text_msg("a1", "agent", "Here are some great options for you."),
        _event_msg("e1", "product_view"),
    ])
    result = analyze(conv)
    assert result["low_engagement_product_rec"] is False


def test_low_engagement_false_when_no_suggestion_text_and_no_events():
    conv = _conv([
        _text_msg("u1", "user", "What are your store hours?"),
        _text_msg("a1", "agent", "We are open Monday through Friday, 9am to 5pm."),
    ])
    result = analyze(conv)
    assert result["low_engagement_product_rec"] is False


def test_low_engagement_false_when_no_suggestion_text_but_events_present():
    conv = _conv([
        _text_msg("u1", "user", "I want to browse."),
        _event_msg("e1", "product_view"),
    ])
    result = analyze(conv)
    assert result["low_engagement_product_rec"] is False


# --- suggestion phrase coverage ---

def test_various_suggestion_phrases_detected():
    phrases = [
        "Here are some options.",
        "You might like this.",
        "Check out our collection.",
        "Take a look at these.",
        "Here's a great pick.",
        "These products are popular.",
        "This product is perfect.",
        "I suggest trying this.",
        "You could try this one.",
        "How about this option?",
        "Consider this alternative.",
        "We have an option for you.",
        "Available in multiple sizes.",
    ]
    for phrase in phrases:
        conv = _conv([_text_msg("a1", "agent", phrase)])
        result = analyze(conv)
        assert result["low_engagement_product_rec"] is True, f"Phrase not detected: {phrase!r}"
