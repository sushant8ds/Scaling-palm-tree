"""Data ingestion module for the Conversation Analysis System.

Connects to MongoDB, queries conversations and messages, joins them,
applies optional filters, and returns a list of EnrichedConversation objects.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from cas.models import Conversation, EnrichedConversation, Message

logger = logging.getLogger(__name__)

_DB_NAME = "helio_intern"
_CONVERSATIONS_COLLECTION = "conversations"
_MESSAGES_COLLECTION = "messages"


def load_data(
    mongo_uri: str,
    widget_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[EnrichedConversation]:
    """Load and join conversation + message data from MongoDB.

    Args:
        mongo_uri: MongoDB connection URI.
        widget_id: Optional brand filter — only conversations with this widgetId are returned.
        date_from: Optional start of date range filter (inclusive) on conversations.createdAt.
        date_to: Optional end of date range filter (inclusive) on conversations.createdAt.

    Returns:
        List of EnrichedConversation objects with messages sorted by timestamp ascending.

    Raises:
        ConnectionError: If the MongoDB connection cannot be established.
    """
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # Force a connection check
        client.admin.command("ping")
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        raise ConnectionError(
            f"Failed to connect to MongoDB at '{mongo_uri}': {exc}"
        ) from exc

    db = client[_DB_NAME]

    # Build conversation query filter
    conv_filter: dict = {}

    if widget_id is not None:
        try:
            conv_filter["widgetId"] = ObjectId(widget_id)
        except Exception:
            # If widget_id is not a valid ObjectId string, store as-is
            conv_filter["widgetId"] = widget_id

    if date_from is not None or date_to is not None:
        created_at_filter: dict = {}
        if date_from is not None:
            created_at_filter["$gte"] = date_from
        if date_to is not None:
            created_at_filter["$lte"] = date_to
        conv_filter["createdAt"] = created_at_filter

    # Fetch matching conversations
    raw_conversations = list(db[_CONVERSATIONS_COLLECTION].find(conv_filter))

    if not raw_conversations:
        return []

    # Build a map of conversation_id (str) -> Conversation
    conversation_map: dict[str, Conversation] = {}
    for doc in raw_conversations:
        conv_id = str(doc["_id"])
        # Handle createdAt/updatedAt stored as string or datetime
        created_at = doc["createdAt"]
        updated_at = doc["updatedAt"]
        if isinstance(created_at, str):
            from datetime import timezone
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        conversation_map[conv_id] = Conversation(
            id=conv_id,
            widget_id=str(doc["widgetId"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    # Fetch all messages for matched conversations
    # Handle both ObjectId and string _id formats (dataset may use either)
    conv_raw_ids = [doc["_id"] for doc in raw_conversations]
    conv_str_ids = [str(doc["_id"]) for doc in raw_conversations]
    # Query with both formats to handle mixed datasets
    raw_messages = list(
        db[_MESSAGES_COLLECTION].find(
            {"conversationId": {"$in": conv_raw_ids + conv_str_ids}}
        )
    )

    # Group messages by conversation_id
    messages_by_conv: dict[str, list[Message]] = defaultdict(list)
    for msg_doc in raw_messages:
        conv_id = str(msg_doc["conversationId"])
        if conv_id not in conversation_map:
            # Orphaned message — skip
            logger.warning(
                "Message %s references unknown conversationId %s — skipping.",
                str(msg_doc["_id"]),
                conv_id,
            )
            continue

        # Handle timestamp stored as string or datetime
        ts = msg_doc["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        message = Message(
            id=str(msg_doc["_id"]),
            conversation_id=conv_id,
            sender=msg_doc.get("sender", ""),
            message_type=msg_doc.get("messageType", "text"),
            text=msg_doc.get("text", ""),
            timestamp=ts,
            metadata=msg_doc.get("metadata") or {},
        )
        messages_by_conv[conv_id].append(message)

    # Build EnrichedConversation list, excluding zero-message conversations
    enriched: list[EnrichedConversation] = []
    for conv_id, conversation in conversation_map.items():
        msgs = messages_by_conv.get(conv_id, [])
        if not msgs:
            logger.warning(
                "Conversation %s has zero messages — excluding from analysis.", conv_id
            )
            continue

        # Sort messages by timestamp ascending
        sorted_msgs = sorted(msgs, key=lambda m: m.timestamp)
        enriched.append(EnrichedConversation(conversation=conversation, messages=sorted_msgs))

    return enriched
