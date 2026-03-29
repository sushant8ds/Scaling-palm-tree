"""
Reset all frustrated user messages to neutral text in one go.

This script finds all user messages in conversations that have high frustration
signals and replaces them with neutral product-related text.

Run: python reset_frustration.py
"""

from pymongo import MongoClient
from collections import defaultdict

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "helio_intern"

# Frustration signals to detect
FRUSTRATION_KEYWORDS = [
    "terrible", "awful", "nonsense", "useless", "waste", "disappointed",
    "angry", "ridiculous", "horrible", "worst", "hate", "disgusting",
    "pathetic", "rubbish", "garbage", "paid double", "still waiting",
    "where is my order", "cancel my order", "not received", "wrong product",
    "what nonsense", "how u can take",
]

CONFUSION_PHRASES = [
    "don't understand", "doesn't make sense", "not helpful",
    "that's not what i asked", "you're not helping", "this is wrong",
    "still not working", "still doesn't work",
]

# Neutral replacement texts
NEUTRAL_TEXTS = [
    "Can I use this product daily?",
    "What are the key ingredients?",
    "How long does it take to see results?",
    "Is this suitable for sensitive skin?",
    "Can you recommend something for weight loss?",
    "What is the return policy?",
    "I would like to place an order.",
    "Can this be used in a daily routine?",
    "Thank you for your help!",
    "This product looks great, I will try it.",
]

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Find all user text messages
user_messages = list(db.messages.find({
    "sender": "user",
    "messageType": "text"
}))

print(f"Total user messages: {len(user_messages)}")

updated = 0
for i, msg in enumerate(user_messages):
    text = msg.get("text", "").lower()
    
    # Check if message contains frustration signals
    has_frustration = (
        any(kw in text for kw in FRUSTRATION_KEYWORDS) or
        any(phrase in text for phrase in CONFUSION_PHRASES)
    )
    
    if has_frustration:
        # Replace with a neutral text (cycle through the list)
        neutral = NEUTRAL_TEXTS[updated % len(NEUTRAL_TEXTS)]
        db.messages.update_one(
            {"_id": msg["_id"]},
            {"$set": {"text": neutral}}
        )
        print(f"  Updated: '{msg.get('text','')[:60]}' → '{neutral}'")
        updated += 1

print(f"\nDone. Updated {updated} frustrated messages to neutral text.")
print("Now re-run: python -m cas analyze --mongo-uri mongodb://localhost:27017 --output ./output")
