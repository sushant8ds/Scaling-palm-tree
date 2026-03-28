"""
Explore what phrases the assistant actually uses in your dataset.

Prints:
1. Agent messages that were followed by product engagement events
   (these are the "successful" suggestion messages)
2. Top bigrams and trigrams from those messages
3. All unique eventTypes found in the dataset
"""

from collections import Counter
from pymongo import MongoClient
from bson import ObjectId

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "helio_intern"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Load all conversations and messages
print("Loading data...")
conversations = list(db.conversations.find())
conv_ids = [c["_id"] for c in conversations]
messages = list(db.messages.find({"conversationId": {"$in": conv_ids}}))

# Group messages by conversation, sorted by timestamp
from collections import defaultdict
conv_messages = defaultdict(list)
for msg in messages:
    conv_messages[str(msg["conversationId"])].append(msg)

for cid in conv_messages:
    conv_messages[cid].sort(key=lambda m: m.get("timestamp", 0))

# Find all unique event types
print("\n--- ALL EVENT TYPES IN DATASET ---")
event_types = Counter()
for msg in messages:
    if msg.get("messageType") == "event":
        et = msg.get("metadata", {}).get("eventType", "UNKNOWN")
        event_types[et] += 1
for et, count in event_types.most_common():
    print(f"  {et}: {count}")

# Find agent messages followed by product events
PRODUCT_EVENTS = {"product_view", "product_click", "add_to_cart"}
successful_agent_msgs = []

for cid, msgs in conv_messages.items():
    for i, msg in enumerate(msgs):
        if msg.get("messageType") != "text" or msg.get("sender") != "agent":
            continue
        # Look ahead up to 3 messages for a product event
        for j in range(i + 1, min(i + 4, len(msgs))):
            next_msg = msgs[j]
            if (next_msg.get("messageType") == "event" and
                    next_msg.get("metadata", {}).get("eventType", "") in PRODUCT_EVENTS):
                successful_agent_msgs.append(msg.get("text", ""))
                break

print(f"\n--- AGENT MESSAGES FOLLOWED BY PRODUCT EVENTS: {len(successful_agent_msgs)} found ---")
if successful_agent_msgs:
    print("\nSample messages (first 5):")
    for i, text in enumerate(successful_agent_msgs[:5]):
        print(f"\n[{i+1}] {text[:300]}")
else:
    print("None found — no agent messages were directly followed by product engagement events.")
    print("This means the fallback phrase list is being used.")

# Extract bigrams and trigrams from successful messages
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "i", "you", "we", "it",
    "to", "of", "in", "for", "on", "with", "at", "by", "and", "or", "but",
    "this", "that", "these", "those", "my", "your", "our", "be", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "can", "not", "no", "so", "if", "as", "up", "out",
    "also", "just", "very", "here", "there", "what", "how", "when", "where",
}

bigrams = Counter()
trigrams = Counter()

for text in successful_agent_msgs:
    words = [
        w.lower().strip(".,!?;:'\"")
        for w in text.split()
        if w.lower().strip(".,!?;:'\"") not in STOPWORDS and len(w) > 2
    ]
    for i in range(len(words) - 1):
        bigrams[f"{words[i]} {words[i+1]}"] += 1
    for i in range(len(words) - 2):
        trigrams[f"{words[i]} {words[i+1]} {words[i+2]}"] += 1

if bigrams:
    print("\n--- TOP 20 BIGRAMS (from successful suggestion messages) ---")
    for phrase, count in bigrams.most_common(20):
        print(f"  '{phrase}': {count}")

if trigrams:
    print("\n--- TOP 20 TRIGRAMS (from successful suggestion messages) ---")
    for phrase, count in trigrams.most_common(20):
        print(f"  '{phrase}': {count}")

# Also show all agent messages that contain product-related words
print("\n--- SAMPLE AGENT MESSAGES CONTAINING PRODUCT WORDS ---")
product_words = {"product", "item", "recommend", "suggest", "option", "available", "check", "look"}
samples = []
for msg in messages:
    if msg.get("sender") == "agent" and msg.get("messageType") == "text":
        text = msg.get("text", "").lower()
        if any(w in text for w in product_words):
            samples.append(msg.get("text", ""))

print(f"Found {len(samples)} agent messages with product-related words.")
print("\nFirst 3 samples:")
for i, text in enumerate(samples[:3]):
    print(f"\n[{i+1}] {text[:400]}")
