"""Conversation segmentation analyzer.

Classifies conversations by topic and flags unanswered conversations.

Dataset findings (from direct exploration of this dataset):
- Brands: Blue Nectar (Ayurvedic skincare), Blue Tea (herbal teas), Sri Sri Tattva
- Top user topics by word frequency:
  order(89), tea(46), weight(32), fat(25), ingredients(16), offer(20),
  cancel(10), skin(9), serum(8), cream(14), routine(24), results(23)
- Dataset-specific topic patterns:
  * "What are the key ingredients?" — product ingredient queries
  * "Can this be used in a daily routine?" — usage queries
  * "How long does it take to see results?" — efficacy queries
  * "Need help to place an order" / "How to cancel my order" — order issues
  * "Offers are there now" / "I need discount" — promotions
  * "Can I place an international order" — shipping/international
  * "Can you generate a OTP" — checkout/OTP issues
  * Hindi queries: "hai", "Namaste", "kya" — multilingual support
These are combined with generic e-commerce topic keywords for full coverage.
"""

from __future__ import annotations

from cas.models import EnrichedConversation, Message

# Keyword sets per topic category
# Each category has: generic keywords (future-proof) + dataset-specific keywords
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "product_question": [
        # Generic
        "what", "how", "does", "is", "are", "tell me about", "describe",
        "specs", "features", "details", "color", "size", "material", "weight",
        "benefits", "side effects", "safe", "suitable",
        # Dataset-specific (from exploration)
        "key ingredients", "ingredients", "ingredient",  # "What are the key ingredients?"
        "daily routine", "routine",                       # "Can this be used in a daily routine?"
        "see results", "results", "how long",             # "How long does it take to see results?"
        "acne", "skin", "serum", "cream", "oil", "face",  # skincare product queries
        "tea", "herbal", "belly fat", "weight loss",       # herbal tea product queries
        "ghee", "shampoo", "hair",                         # other product categories
        "post natal", "sensitive", "coconut",              # specific product concerns
        "under eye", "whitening", "brightening",           # skincare concerns
    ],
    "order_issue": [
        # Generic
        "order", "delivery", "shipping", "track", "return", "refund", "cancel",
        "damaged", "missing", "wrong item", "not received",
        # Dataset-specific
        "cancel my order", "how to cancel",               # "How to cancel my order.?"
        "where is my order",                               # repeated in bad conversations
        "place an order", "place order",                   # "Need help to place an order"
        "checkout", "check out",                           # "Need to check out but no option"
        "edit", "edit order",                              # "edit" appeared in bad conversations
        "international order", "uk", "england",            # international shipping queries
        "otp", "otp code",                                 # "Can I place an international order without an OTP"
        "netar points", "points",                          # loyalty points
        "add to cart", "cart",                             # cart issues
    ],
    "recommendation_request": [
        # Generic
        "recommend", "suggest", "best", "which", "what should", "looking for",
        "help me find", "similar",
        # Dataset-specific
        "for weight loss", "weight loss",                  # "For weight loss, we have..."
        "for fat reduction", "fat reduction",
        "for skin", "for acne", "for hair",
        "skin colour whitening",                           # "Skin colour whitening cream"
        "which product", "which one",
    ],
    "policy_inquiry": [
        # Generic
        "policy", "warranty", "guarantee", "terms", "conditions",
        "return policy", "exchange", "store credit",
        # Dataset-specific
        "offer", "offers", "discount", "sale",             # "Offers are there now", "I need discount"
        "buy one get one", "bogo", "buy 1 get 1",
        "buy three", "3 items",                            # "Offer 3 items @ 1595"
        "when is the next offer",
        "netar points", "loyalty",                         # loyalty program
    ],
    "checkout_support": [
        # Dataset-specific category — very common in this dataset
        "otp", "generate otp", "otp code",
        "place an order", "place order",
        "checkout", "check out",
        "payment", "pay",
        "international order", "order from uk",
        "phone number",
    ],
}


def _classify_message(text: str) -> list[str]:
    """Return matching topic categories for a single message text."""
    lower = text.lower()
    matched = [
        category
        for category, keywords in _TOPIC_KEYWORDS.items()
        if any(kw in lower for kw in keywords)
    ]
    return matched


def _partition_messages(messages: list[Message]) -> tuple[list[Message], list[Message]]:
    """Split messages into (text_messages, event_messages)."""
    text_msgs = [m for m in messages if m.message_type == "text"]
    event_msgs = [m for m in messages if m.message_type == "event"]
    return text_msgs, event_msgs


def analyze(conv: EnrichedConversation) -> dict:
    """Analyze a conversation for topic categories and unanswered status.

    Returns a partial result dict with:
        - topic_categories: list[str]
        - is_unanswered: bool
    """
    text_messages, _event_messages = _partition_messages(conv.messages)

    # Determine unanswered: no agent messages at all
    is_unanswered = not any(m.sender == "agent" for m in conv.messages)

    # Classify based on user text messages only
    user_text_messages = [m for m in text_messages if m.sender == "user"]

    categories: list[str] = []
    for msg in user_text_messages:
        categories.extend(_classify_message(msg.text))

    # Deduplicate while preserving first-seen order
    seen: set[str] = set()
    unique_categories: list[str] = []
    for cat in categories:
        if cat not in seen:
            seen.add(cat)
            unique_categories.append(cat)

    # Fallback to "general" if no category matched
    if not unique_categories:
        unique_categories = ["general"]

    return {
        "topic_categories": unique_categories,
        "is_unanswered": is_unanswered,
    }
