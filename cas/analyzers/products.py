"""Product suggestion analyzer.

Detects product engagement events and flags low-engagement product recommendations.

Dataset findings (from explore_phrases.py on this dataset):
- Brands: Blue Nectar (Ayurvedic skincare), Blue Tea (herbal teas), Sri Sri Tattva
- Agent messages embed markdown links [Product Name](https://...) when suggesting products
  — this is the PRIMARY detection signal for this dataset
- 43 agent messages were followed by product engagement events
- Top suggestion language: "excellent choice", "ideal choice", "top choices",
  "excellent options", "specifically crafted", "designed to boost"
- Event types found: product_view(33), similar_product_click(4), link_click(179)
- 499/629 agent messages contain "End of stream {...}" JSON — must be stripped
These are combined with generic e-commerce phrases for full coverage.
"""

from __future__ import annotations

import re
from collections import Counter

from cas.models import EnrichedConversation

# Event types that count as product engagement
# Generic types + dataset-specific types found by exploration
_PRODUCT_EVENT_TYPES: frozenset[str] = frozenset({
    # Generic
    "product_view",
    "product_click",
    "add_to_cart",
    # Dataset-specific (found in this dataset)
    "similar_product_click",
    "link_click",
})

# Primary detection: markdown product links in agent messages
# Matches [Any Text](https://...) — the pattern used in this dataset
_MARKDOWN_LINK_RE = re.compile(r'\[.+?\]\(https?://\S+\)', re.I)

# Stopwords for phrase extraction
_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "i", "you", "we", "it",
    "to", "of", "in", "for", "on", "with", "at", "by", "and", "or", "but",
    "this", "that", "these", "those", "my", "your", "our", "be", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "can", "not", "no", "so", "if", "as", "up", "out",
    "also", "just", "very", "here", "there", "what", "how", "when", "where",
})

# Learned phrases from dataset — populated by learn_suggestion_phrases()
_learned_phrases: list[re.Pattern] = []

# Hardcoded phrases — generic e-commerce language + dataset-specific patterns
# ALL run together (not either/or) for maximum coverage
_FALLBACK_PHRASES: list[re.Pattern] = [
    # Generic recommendation phrases (future-proof for any brand)
    re.compile(r"here are some", re.I),
    re.compile(r"i recommend", re.I),
    re.compile(r"you might like", re.I),
    re.compile(r"check out", re.I),
    re.compile(r"take a look at", re.I),
    re.compile(r"here'?s a", re.I),
    re.compile(r"these products", re.I),
    re.compile(r"this product", re.I),
    re.compile(r"i suggest", re.I),
    re.compile(r"you could try", re.I),
    re.compile(r"how about", re.I),
    re.compile(r"\bconsider\b", re.I),
    re.compile(r"\boption\b", re.I),
    re.compile(r"available in", re.I),
    # Dataset-specific patterns (from explore_phrases.py on this dataset)
    re.compile(r"excellent choice", re.I),       # "is an excellent choice"
    re.compile(r"ideal choice", re.I),            # "is your ideal choice"
    re.compile(r"top choices", re.I),             # "here are our top choices"
    re.compile(r"excellent options", re.I),       # "we have excellent options"
    re.compile(r"great options", re.I),
    re.compile(r"specifically crafted", re.I),    # "specifically crafted to address"
    re.compile(r"designed to", re.I),             # "designed to boost metabolism"
    re.compile(r"perfect for", re.I),
    re.compile(r"best for", re.I),
    re.compile(r"our .{1,30} is", re.I),          # "our Belly Fat Tea is..."
]


def _clean_agent_text(text: str) -> str:
    """Strip 'End of stream {...}' JSON noise from agent messages.

    Found in 499/629 agent messages in this dataset.
    """
    idx = text.find("End of stream")
    if idx != -1:
        return text[:idx].strip()
    return text


def learn_suggestion_phrases(
    conversations: list[EnrichedConversation],
    top_n: int = 20,
) -> None:
    """Learn product suggestion phrases from agent messages that preceded engagement events.

    Finds agent messages followed by product engagement events, extracts
    bigrams from the surrounding language (not product names), and stores
    them as learned patterns.
    """
    global _learned_phrases

    bigram_counts: Counter = Counter()

    for conv in conversations:
        msgs = conv.messages
        for idx, msg in enumerate(msgs):
            if msg.message_type != "text" or msg.sender != "agent":
                continue

            followed_by_engagement = any(
                msgs[j].message_type == "event"
                and msgs[j].metadata.get("eventType", "") in _PRODUCT_EVENT_TYPES
                for j in range(idx + 1, min(idx + 4, len(msgs)))
            )

            if not followed_by_engagement:
                continue

            clean_text = _clean_agent_text(msg.text)
            # Remove markdown links — focus on surrounding language, not product names
            clean_text = _MARKDOWN_LINK_RE.sub("", clean_text)

            words = [
                w.lower().strip(".,!?;:'\"*")
                for w in clean_text.split()
                if w.lower().strip(".,!?;:'\"*") not in _STOPWORDS
                and len(w) > 2
            ]

            for i in range(len(words) - 1):
                bigram_counts[f"{words[i]} {words[i+1]}"] += 1

    candidates = [(p, c) for p, c in bigram_counts.most_common(top_n * 2) if c >= 2]

    seen: set[str] = set()
    patterns: list[re.Pattern] = []
    for phrase, _ in candidates:
        if phrase not in seen:
            seen.add(phrase)
            patterns.append(re.compile(re.escape(phrase), re.I))

    if patterns:
        _learned_phrases = patterns[:top_n]
        import logging
        logging.getLogger(__name__).info(
            "Learned %d product suggestion phrases from dataset: %s",
            len(_learned_phrases),
            ", ".join(p.pattern for p in _learned_phrases[:5])
            + ("..." if len(_learned_phrases) > 5 else ""),
        )


def _has_product_suggestion(text: str) -> bool:
    """Detect if agent message contains a product suggestion.

    Uses ALL signals together — no priority, all run:
    1. Markdown product link (primary signal for this dataset)
    2. Dataset-learned phrases (data-driven bigrams from successful suggestions)
    3. Generic + dataset-specific hardcoded phrases (always active)
    """
    clean = _clean_agent_text(text)

    if _MARKDOWN_LINK_RE.search(clean):
        return True

    if any(pattern.search(clean) for pattern in _learned_phrases):
        return True

    return any(pattern.search(clean) for pattern in _FALLBACK_PHRASES)


def analyze(conv: EnrichedConversation) -> dict:
    """Analyze a conversation for product engagement and low-engagement recommendations."""
    product_engagement = False
    agent_made_suggestion = False

    for msg in conv.messages:
        if msg.message_type == "event":
            event_type = msg.metadata.get("eventType", "")
            if event_type in _PRODUCT_EVENT_TYPES:
                product_engagement = True
        elif msg.message_type == "text" and msg.sender == "agent":
            if _has_product_suggestion(msg.text):
                agent_made_suggestion = True

    low_engagement_product_rec = agent_made_suggestion and not product_engagement

    return {
        "product_engagement": product_engagement,
        "low_engagement_product_rec": low_engagement_product_rec,
    }
