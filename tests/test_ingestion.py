"""Unit tests for cas/ingestion.py using mongomock."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from cas.ingestion import load_data, _DB_NAME, _CONVERSATIONS_COLLECTION, _MESSAGES_COLLECTION


def _make_client(uri, **kwargs):
    """Return a mongomock client (ignores URI and extra kwargs)."""
    return mongomock.MongoClient()


def _seed(client, conversations=(), messages=()):
    db = client[_DB_NAME]
    if conversations:
        db[_CONVERSATIONS_COLLECTION].insert_many(conversations)
    if messages:
        db[_MESSAGES_COLLECTION].insert_many(messages)
    return db


def _ts(year, month=1, day=1, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _conv_doc(widget_id="brand1", created_at=None, updated_at=None):
    from bson import ObjectId
    return {
        "_id": ObjectId(),
        "widgetId": widget_id,
        "createdAt": created_at or _ts(2024, 1, 1),
        "updatedAt": updated_at or _ts(2024, 1, 2),
    }


def _msg_doc(conv_id, timestamp, sender="user", text="hello"):
    from bson import ObjectId
    return {
        "_id": ObjectId(),
        "conversationId": conv_id,
        "sender": sender,
        "messageType": "text",
        "text": text,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadDataEmpty:
    def test_returns_empty_list_when_no_conversations(self):
        with patch("cas.ingestion.MongoClient", side_effect=_make_client):
            result = load_data("mongodb://localhost:27017")
        assert result == []


class TestZeroMessageExclusion:
    def test_excludes_conversations_with_no_messages(self):
        mock_client = mongomock.MongoClient()
        conv = _conv_doc()
        _seed(mock_client, conversations=[conv])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017")

        assert result == []

    def test_includes_conversations_that_have_messages(self):
        mock_client = mongomock.MongoClient()
        conv = _conv_doc()
        msg = _msg_doc(conv["_id"], _ts(2024, 1, 1, 10))
        _seed(mock_client, conversations=[conv], messages=[msg])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017")

        assert len(result) == 1


class TestMessageSortOrder:
    def test_messages_sorted_by_timestamp_ascending(self):
        mock_client = mongomock.MongoClient()
        conv = _conv_doc()
        msgs = [
            _msg_doc(conv["_id"], _ts(2024, 1, 1, 12), text="third"),
            _msg_doc(conv["_id"], _ts(2024, 1, 1, 8),  text="first"),
            _msg_doc(conv["_id"], _ts(2024, 1, 1, 10), text="second"),
        ]
        _seed(mock_client, conversations=[conv], messages=msgs)

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017")

        assert len(result) == 1
        texts = [m.text for m in result[0].messages]
        assert texts == ["first", "second", "third"]


class TestConnectionError:
    def test_raises_connection_error_on_failure(self):
        def _failing_client(uri, **kwargs):
            raise ServerSelectionTimeoutError("timeout")

        with patch("cas.ingestion.MongoClient", side_effect=_failing_client):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                load_data("mongodb://invalid:27017")


class TestWidgetIdFilter:
    def test_widget_id_filter_returns_only_matching_conversations(self):
        mock_client = mongomock.MongoClient()
        conv_a = _conv_doc(widget_id="brand_a")
        conv_b = _conv_doc(widget_id="brand_b")
        msg_a = _msg_doc(conv_a["_id"], _ts(2024, 1, 1, 9), text="msg_a")
        msg_b = _msg_doc(conv_b["_id"], _ts(2024, 1, 1, 9), text="msg_b")
        _seed(mock_client, conversations=[conv_a, conv_b], messages=[msg_a, msg_b])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017", widget_id="brand_a")

        assert len(result) == 1
        assert result[0].conversation.widget_id == "brand_a"

    def test_widget_id_filter_returns_empty_when_no_match(self):
        mock_client = mongomock.MongoClient()
        conv = _conv_doc(widget_id="brand_x")
        msg = _msg_doc(conv["_id"], _ts(2024, 1, 1, 9))
        _seed(mock_client, conversations=[conv], messages=[msg])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017", widget_id="brand_y")

        assert result == []


class TestDateRangeFilter:
    def test_date_from_excludes_older_conversations(self):
        mock_client = mongomock.MongoClient()
        old_conv = _conv_doc(created_at=_ts(2023, 6, 1))
        new_conv = _conv_doc(created_at=_ts(2024, 3, 1))
        msg_old = _msg_doc(old_conv["_id"], _ts(2023, 6, 1, 10))
        msg_new = _msg_doc(new_conv["_id"], _ts(2024, 3, 1, 10))
        _seed(mock_client, conversations=[old_conv, new_conv], messages=[msg_old, msg_new])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017", date_from=_ts(2024, 1, 1))

        assert len(result) == 1
        # mongomock strips tzinfo; compare naive equivalent
        assert result[0].conversation.created_at.replace(tzinfo=None) == datetime(2024, 3, 1)

    def test_date_to_excludes_newer_conversations(self):
        mock_client = mongomock.MongoClient()
        old_conv = _conv_doc(created_at=_ts(2023, 6, 1))
        new_conv = _conv_doc(created_at=_ts(2024, 3, 1))
        msg_old = _msg_doc(old_conv["_id"], _ts(2023, 6, 1, 10))
        msg_new = _msg_doc(new_conv["_id"], _ts(2024, 3, 1, 10))
        _seed(mock_client, conversations=[old_conv, new_conv], messages=[msg_old, msg_new])

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data("mongodb://localhost:27017", date_to=_ts(2023, 12, 31))

        assert len(result) == 1
        assert result[0].conversation.created_at.replace(tzinfo=None) == datetime(2023, 6, 1)

    def test_date_range_both_bounds(self):
        mock_client = mongomock.MongoClient()
        convs = [
            _conv_doc(created_at=_ts(2023, 1, 1)),
            _conv_doc(created_at=_ts(2024, 1, 15)),
            _conv_doc(created_at=_ts(2025, 1, 1)),
        ]
        msgs = [_msg_doc(c["_id"], c["createdAt"]) for c in convs]
        _seed(mock_client, conversations=convs, messages=msgs)

        with patch("cas.ingestion.MongoClient", return_value=mock_client):
            result = load_data(
                "mongodb://localhost:27017",
                date_from=_ts(2024, 1, 1),
                date_to=_ts(2024, 12, 31),
            )

        assert len(result) == 1
        assert result[0].conversation.created_at.replace(tzinfo=None) == datetime(2024, 1, 15)
