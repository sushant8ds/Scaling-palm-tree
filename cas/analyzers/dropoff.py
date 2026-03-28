"""Drop-off and frustration analyzer.

Detects conversation drop-offs and computes a frustration score using:
- Signal 1 (weight 0.4): Sentiment — ALL three layers run together:
    a) Dataset-learned keywords (TF-IDF log-odds from this dataset)
    b) Generic negative sentiment keywords (future-proof)
    c) Dataset-specific keywords found by direct exploration
- Signal 2 (weight 0.3): Confusion/dissatisfaction phrases (generic + dataset-specific)
- Signal 3 (weight 0.3): Behavioral repetition detection

Dataset findings (from direct exploration):
- Frustration signals: "paid double", "payment", "nonsense", "200 rs for shipping"
- Order issues dominate bad conversations: "cancel", "order", "where is my order"
- Direct expressions: "What nonsense", "How u can take 200 rs"
"""

from __future__ import annotations

import functools

from cas.models import EnrichedConversation, Message

# Signal 2: Confusion/dissatisfaction phrases (weight 0.3)
# Generic phrases + dataset-specific patterns found by exploration
_CONFUSION_PHRASES: list[str] = [
    # Generic interaction failure phrases
    "don't understand", "doesn't make sense", "not helpful",
    "that's not what i asked", "you're not helping", "this is wrong",
    "still not working", "still doesn't work", "not what i wanted",
    "that's wrong", "incorrect",
    # Dataset-specific frustration expressions (found in bad conversations)
    "what nonsense",           # direct frustration expression seen in dataset
    "how u can take",          # "how u can take 200 rs for shipping"
    "paid double",             # payment issue
    "where is my order",       # repeated order query (top bad-conversation phrase)
    "cancel my order",         # cancellation frustration
    "not received",            # order not received
    "wrong product",           # wrong item delivered
    "still waiting",           # unresolved wait
]

# Dataset-specific hardcoded keywords (from direct exploration of this dataset)
# Combined with generic keywords for full coverage across current + future brands
_DATASET_KEYWORDS: list[str] = [
    # From log-odds analysis: top words in bad conversations
    "paid", "double", "payment", "nonsense", "cancel",
    "amount", "refund", "charged", "overcharged",
    # Order frustration patterns seen in bad messages
    "where", "missing", "delayed", "late",
]

_STOPWORDS: frozenset[str] = frozenset([
    "the", "a", "is", "what", "how", "can", "you", "i", "my", "me", "it",
])

# Dataset-derived keywords — populated by calling learn_keywords() before analysis
_learned_keywords: list[str] = []


def learn_keywords(conversations: list[EnrichedConversation]) -> None:
    """Extract frustration keywords from the dataset and store them globally.

    Call this once before running analyze() on individual conversations.
    The keywords are derived from words that appear disproportionately in
    drop-off / unresolved conversations vs normal ones.
    """
    global _learned_keywords
    from cas.analyzers.keyword_extractor import extract_frustration_keywords
    _learned_keywords = extract_frustration_keywords(conversations, top_n=40)
    if _learned_keywords:
        import logging
        logging.getLogger(__name__).info(
            "Learned %d frustration keywords from dataset: %s",
            len(_learned_keywords),
            ", ".join(_learned_keywords[:10]) + ("..." if len(_learned_keywords) > 10 else ""),
        )


@functools.lru_cache(maxsize=1)
def _get_sentiment_pipeline():
    """Load the sentiment model once and cache it. Used as fallback only."""
    try:
        from transformers import pipeline
        return pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            truncation=True,
            max_length=512,
        )
    except Exception:
        return None


def _user_text_messages(messages: list[Message]) -> list[Message]:
    return [m for m in messages if m.sender == "user" and m.message_type == "text"]


def _sentiment_score(user_msgs: list[Message]) -> float:
    """Score using ALL keyword layers together — no priority, all run.

    Layer 1: Dataset-learned keywords (TF-IDF from this specific dataset)
    Layer 2: Dataset-specific hardcoded keywords (from direct exploration)
    Layer 3: Generic negative sentiment keywords (future-proof)
    Layer 4: Pre-trained sentiment model fallback (catches anything else)

    A message is counted as negative if ANY layer triggers.
    """
    if not user_msgs:
        return 0.0

    # Generic negative keywords (future-proof for any brand)
    _GENERIC_KEYWORDS = [
        "frustrated", "annoyed", "terrible", "awful", "useless", "waste",
        "disappointed", "angry", "ridiculous", "unacceptable", "horrible",
        "worst", "hate", "disgusting", "pathetic", "rubbish", "garbage",
        "clueless", "incompetent", "broken", "stupid", "ridiculous",
        "scam", "fraud", "cheating", "lied", "fake",
    ]

    all_keywords = list(_DATASET_KEYWORDS) + _GENERIC_KEYWORDS
    if _learned_keywords:
        all_keywords = list(_learned_keywords) + all_keywords

    triggered = sum(
        1 for m in user_msgs
        if any(kw in m.text.lower() for kw in all_keywords)
    )

    # If keyword layers found nothing, try the sentiment model as a catch-all
    if triggered == 0:
        pipe = _get_sentiment_pipeline()
        if pipe is not None:
            texts = [m.text[:512] for m in user_msgs]
            try:
                results = pipe(texts)
                triggered = sum(1 for r in results if r["label"] == "NEGATIVE")
            except Exception:
                pass

    return triggered / len(user_msgs)


def _confusion_score(user_msgs: list[Message]) -> float:
    """Fraction of user messages containing at least one confusion phrase."""
    if not user_msgs:
        return 0.0
    triggered = sum(
        1 for m in user_msgs
        if any(phrase in m.text.lower() for phrase in _CONFUSION_PHRASES)
    )
    return triggered / len(user_msgs)


def _significant_words(text: str) -> set[str]:
    """Return lowercase words from text, excluding stopwords."""
    words = text.lower().split()
    return {w.strip(".,!?;:'\"") for w in words if w.strip(".,!?;:'\"") not in _STOPWORDS}


def _repetition_score(user_msgs: list[Message]) -> float:
    """Score based on repeated/similar questions among user messages."""
    if len(user_msgs) < 2:
        return 0.0

    word_sets = [_significant_words(m.text) for m in user_msgs]
    repeated: set[int] = set()

    for i in range(len(word_sets)):
        for j in range(i + 1, len(word_sets)):
            common = word_sets[i] & word_sets[j]
            if len(common) >= 2:
                repeated.add(i)
                repeated.add(j)

    return len(repeated) / len(user_msgs)


def analyze(conv: EnrichedConversation) -> dict:
    """Analyze a conversation for drop-off and frustration.

    Returns:
        - is_drop_off: bool
        - frustration_score: float in [0.0, 1.0]
    """
    messages = conv.messages

    # Drop-off: last text message has sender="user" with no subsequent agent reply
    text_messages = [m for m in messages if m.message_type == "text"]
    if text_messages:
        last_text = text_messages[-1]
        is_drop_off = last_text.sender == "user"
    else:
        is_drop_off = False

    # Frustration scoring — three complementary signals
    user_msgs = _user_text_messages(messages)
    s_score = _sentiment_score(user_msgs)   # model-based, catches any negative language
    c_score = _confusion_score(user_msgs)   # rule-based, catches interaction failures
    r_score = _repetition_score(user_msgs)  # behavioral, catches unresolved intent

    frustration_score = min(1.0, 0.4 * s_score + 0.3 * c_score + 0.3 * r_score)

    return {
        "is_drop_off": is_drop_off,
        "frustration_score": frustration_score,
    }
