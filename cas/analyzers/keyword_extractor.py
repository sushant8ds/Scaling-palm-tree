"""Data-driven keyword extraction for frustration detection.

Uses TF-IDF log-odds to discover which words appear disproportionately in
'bad' conversations (drop-offs, short unresolved exchanges) vs normal ones.
These become the frustration signal keywords, grounded in the actual dataset.

Dataset findings (from direct exploration of this dataset):
- Bad conversations dominated by order/payment issues:
  "paid", "double", "payment", "days", "cancel", "order", "amount"
- Direct frustration: "nonsense", "how u can take 200 rs for shipping"
- Repeated questions: "Where is my order?" appearing multiple times
The log-odds extraction picks these up automatically at runtime.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from cas.models import EnrichedConversation

# Basic English stopwords — we want content words only
_STOPWORDS: frozenset[str] = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
    "at", "by", "from", "up", "about", "into", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "this", "that", "these", "those", "and", "but", "or",
    "so", "not", "no", "just", "also", "very", "how", "what", "when",
    "where", "why", "which", "who", "all", "any", "some", "more", "than",
    "too", "s", "t", "don", "doesn", "didn", "won", "can", "hi", "hello",
    "hey", "ok", "okay", "yes", "yeah", "no", "please", "thank", "thanks",
])


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words."""
    words = re.findall(r"[a-z']+", text.lower())
    return [w.strip("'") for w in words if w.strip("'") and w.strip("'") not in _STOPWORDS and len(w) > 2]


def _is_bad_conversation(conv: EnrichedConversation) -> bool:
    """Classify a conversation as 'bad' (likely frustrated user).

    A conversation is bad if:
    - It ends with a user message (drop-off), OR
    - It has very few agent replies relative to user messages (unresolved)
    """
    text_msgs = [m for m in conv.messages if m.message_type == "text"]
    if not text_msgs:
        return False

    # Drop-off signal
    if text_msgs[-1].sender == "user":
        return True

    # Unresolved: user sent 3+ messages but agent replied only once
    user_count = sum(1 for m in text_msgs if m.sender == "user")
    agent_count = sum(1 for m in text_msgs if m.sender == "agent")
    if user_count >= 3 and agent_count <= 1:
        return True

    return False


def extract_frustration_keywords(
    conversations: list[EnrichedConversation],
    top_n: int = 30,
) -> list[str]:
    """Extract the top-N frustration keywords from the dataset using TF-IDF.

    Compares word frequencies in 'bad' conversations vs 'good' ones.
    Words that are significantly more common in bad conversations are
    returned as frustration signals.

    Args:
        conversations: All enriched conversations from the dataset.
        top_n: Number of keywords to return.

    Returns:
        List of keywords ranked by frustration signal strength.
    """
    bad_word_counts: Counter = Counter()
    good_word_counts: Counter = Counter()
    bad_doc_count = 0
    good_doc_count = 0

    for conv in conversations:
        user_text = " ".join(
            m.text for m in conv.messages
            if m.sender == "user" and m.message_type == "text"
        )
        words = _tokenize(user_text)
        if not words:
            continue

        if _is_bad_conversation(conv):
            bad_word_counts.update(set(words))  # document frequency (not term freq)
            bad_doc_count += 1
        else:
            good_word_counts.update(set(words))
            good_doc_count += 1

    if bad_doc_count == 0 or good_doc_count == 0:
        return []

    # Score each word by how much more it appears in bad vs good conversations
    # Score = log( (bad_df / bad_total) / (good_df / good_total + epsilon) )
    # This is essentially a log-odds ratio
    scores: dict[str, float] = {}
    all_words = set(bad_word_counts.keys()) | set(good_word_counts.keys())

    for word in all_words:
        bad_freq = bad_word_counts.get(word, 0) / bad_doc_count
        good_freq = good_word_counts.get(word, 0) / good_doc_count

        # Only consider words that appear in at least 2 bad conversations
        if bad_word_counts.get(word, 0) < 2:
            continue

        # Log-odds ratio — positive means more common in bad conversations
        score = math.log((bad_freq + 1e-9) / (good_freq + 1e-9))
        if score > 0:
            scores[word] = score

    ranked = sorted(scores, key=lambda w: scores[w], reverse=True)
    return ranked[:top_n]
