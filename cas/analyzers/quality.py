"""Response quality analyzer.

Detects verbose, irrelevant, and potentially hallucinated agent responses.

Dataset findings (from direct exploration of this dataset):
- 499/629 agent messages contain "End of stream {...}" JSON suffix — must be
  stripped before word count and keyword analysis
- Max agent message: 1772 words; avg: 275 words; 90 messages over 500 words
- Agent messages use Indian Rupee prices: ₹1399, ₹1299 (not just $)
- Agent messages contain markdown links: [Product](https://...)
- Brands: Blue Nectar, Blue Tea, Sri Sri Tattva (Ayurvedic/wellness)
- Hallucination risk: specific delivery timelines, ingredient claims,
  offer details that may not match current catalog
These findings are combined with generic quality signals for full coverage.
"""

from __future__ import annotations

import re

from cas.models import EnrichedConversation, FlaggedResponse, Message

_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "up", "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "i", "me", "my", "myself", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "what", "which", "who", "this", "that", "these", "those", "and", "but",
    "or", "nor", "so", "yet", "both", "either", "neither", "not", "no",
    "just", "very", "also", "how", "when", "where", "why", "all", "any",
    "each", "few", "more", "most", "other", "some", "such", "than", "too",
    "s", "t", "don", "doesn", "didn", "won", "can",
})

# Hallucination patterns — generic + dataset-specific
# Generic: USD prices, percentages, shipping timelines, arrival dates
# Dataset-specific: INR prices (₹), "buy X get Y" offers, delivery day claims
_HALLUCINATION_PATTERNS: list[re.Pattern] = [
    # Generic price patterns
    re.compile(r'\$\d+(?:\.\d+)?'),                           # $99.99
    re.compile(r'costs?\s+\$\d+', re.I),
    re.compile(r'price\s+is\s+\$\d+', re.I),
    # Dataset-specific: Indian Rupee prices (found in dataset)
    re.compile(r'₹\s*\d+(?:\.\d+)?'),                         # ₹1399, ₹ 1299
    re.compile(r'rs\.?\s*\d+', re.I),                         # Rs. 200, rs 1399
    re.compile(r'inr\s*\d+', re.I),                           # INR 1399
    # Discount/offer claims
    re.compile(r'\d+(?:\.\d+)?%\s*(?:off|discount)', re.I),   # 50% off
    re.compile(r'buy\s+\d+\s+get\s+\d+', re.I),               # buy 1 get 1 (dataset-specific)
    re.compile(r'buy\s+three\s+for', re.I),                    # buy three for 1395 (dataset-specific)
    # Shipping/delivery claims
    re.compile(r'ships?\s+in\s+\d+\s+days?', re.I),           # ships in 3 days
    re.compile(r'deliver(?:ed|y)?\s+in\s+\d+\s+days?', re.I), # delivered in 5 days
    re.compile(r'arrives?\s+by\s+[A-Za-z]+\s+\d+', re.I),     # arrives by January 15
    # Availability claims
    re.compile(r'available\s+in\s+\d+\s+\w+', re.I),          # available in 5 colors
    # Dataset-specific: results/efficacy claims (common in wellness brands)
    re.compile(r'results?\s+in\s+\d+\s+(?:days?|weeks?)', re.I),  # results in 2 weeks
    re.compile(r'see\s+results?\s+in\s+\d+', re.I),               # see results in 4 weeks
]

# "End of stream" JSON suffix found in 499/629 agent messages in this dataset
_END_OF_STREAM_RE = re.compile(r'End of stream\s*\{.*', re.DOTALL)


def _clean_agent_text(text: str) -> str:
    """Strip 'End of stream {...}' JSON noise from agent messages.

    Found in 499/629 agent messages in this dataset. Must be removed
    before word count and keyword analysis to avoid false positives.
    """
    return _END_OF_STREAM_RE.sub("", text).strip()


def _significant_words(text: str) -> set[str]:
    """Return lowercase significant words (non-stopwords) from text."""
    words = re.findall(r"[a-z']+", text.lower())
    return {w.strip("'") for w in words if w.strip("'") and w.strip("'") not in _STOPWORDS}


def _check_verbose(msg: Message) -> FlaggedResponse | None:
    """Flag agent responses over 500 words.

    Dataset context: avg agent message is 275 words, max is 1772 words,
    90 messages exceed 500 words. The 'End of stream' JSON is stripped
    first to avoid inflating word counts.
    """
    clean_text = _clean_agent_text(msg.text)
    word_count = len(clean_text.split())
    if word_count > 500:
        return FlaggedResponse(
            message_id=msg.id,
            flag_type="verbose",
            confidence=1.0,
            reason=f"Response exceeds 500 words ({word_count} words)",
        )
    return None


def _check_irrelevant(agent_msg: Message, preceding_user_msg: Message | None) -> FlaggedResponse | None:
    """Flag agent responses with no keyword overlap with the user's query.

    Strips 'End of stream' JSON and markdown links before comparison
    to avoid false positives from boilerplate content.
    """
    if preceding_user_msg is None:
        return None

    # Strip noise from agent message before keyword extraction
    clean_agent_text = _clean_agent_text(agent_msg.text)
    # Also strip markdown links — [text](url) — to focus on actual content words
    clean_agent_text = re.sub(r'\[.+?\]\(https?://\S+\)', '', clean_agent_text)

    user_keywords = _significant_words(preceding_user_msg.text)
    agent_keywords = _significant_words(clean_agent_text)

    if user_keywords and not (user_keywords & agent_keywords):
        return FlaggedResponse(
            message_id=agent_msg.id,
            flag_type="irrelevant",
            confidence=0.7,
            reason="Agent response shares no keywords with user query",
        )
    return None


def _check_hallucination(msg: Message) -> FlaggedResponse | None:
    """Flag agent responses with 2+ unverifiable specific claims.

    Patterns cover both generic claims (USD prices, shipping days) and
    dataset-specific claims (INR prices ₹, 'buy X get Y' offers,
    efficacy timelines like 'results in 2 weeks').
    Requires 2+ matches to reduce false positives.
    """
    clean_text = _clean_agent_text(msg.text)
    matches = sum(1 for pattern in _HALLUCINATION_PATTERNS if pattern.search(clean_text))
    if matches >= 2:
        return FlaggedResponse(
            message_id=msg.id,
            flag_type="hallucination",
            confidence=0.6,
            reason="Response contains unverifiable specific claims (price/availability/date)",
        )
    return None


def analyze(conv: EnrichedConversation) -> dict:
    """Analyze agent responses for quality issues.

    Returns:
        - flagged_responses: list[FlaggedResponse]
    """
    flagged: list[FlaggedResponse] = []
    last_user_msg: Message | None = None

    for msg in conv.messages:
        if msg.message_type != "text":
            if msg.sender == "user":
                last_user_msg = msg
            continue

        if msg.sender == "user":
            last_user_msg = msg
            continue

        # Agent text message — run all checks
        verbose_flag = _check_verbose(msg)
        if verbose_flag:
            flagged.append(verbose_flag)

        irrelevant_flag = _check_irrelevant(msg, last_user_msg)
        if irrelevant_flag:
            flagged.append(irrelevant_flag)

        hallucination_flag = _check_hallucination(msg)
        if hallucination_flag:
            flagged.append(hallucination_flag)

    return {"flagged_responses": flagged}
