"""Unit tests for transport-neutral events, shared logic, and serializers."""
from __future__ import annotations

import asyncio
import json

import pytest

from chat.events import Completed, Delta, Failed, Started
from chat.logic import REPLY, complete_reply, generate_reply, stream_reply


def test_reply():
    assert generate_reply("hello") == REPLY
    assert generate_reply("another request") == REPLY
    assert asyncio.run(complete_reply("hello")) == REPLY


def test_stream_reply_emits_ordered_events_and_matches_reply():
    async def collect():
        return [event async for event in stream_reply("hello", chunk_size=4, delay_seconds=0.0)]

    events = asyncio.run(collect())
    assert len(events) >= 3
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert isinstance(events[0], Started)
    assert events[0].message_id
    deltas = "".join(event.text for event in events if isinstance(event, Delta))
    assert deltas == REPLY
    assert isinstance(events[-1], Completed)
    assert events[-1].reply == REPLY


def test_unicode_preserved_in_events_and_ndjson(monkeypatch):
    from chat import logic
    from chat.serialization import to_ndjson, to_proto

    unicode_reply = "こんにちは🌍✨ café naïve — streaming 🚀"
    monkeypatch.setattr(logic, "REPLY", unicode_reply)

    async def collect():
        return [event async for event in logic.stream_reply("hi", chunk_size=3, delay_seconds=0.0)]

    events = asyncio.run(collect())
    deltas = "".join(event.text for event in events if isinstance(event, Delta))
    assert deltas == unicode_reply

    for event in events:
        line = to_ndjson(event)
        assert line.endswith(b"\n")
        decoded = json.loads(line.decode("utf-8"))
        assert decoded["result"]["sequence"] == event.sequence
        proto_ev = to_proto(event)
        assert proto_ev.sequence == event.sequence


def test_complete_reply_raises_on_failed_event(monkeypatch):
    from chat import logic

    async def failing_stream(text: str, **kwargs):
        _ = text, kwargs
        yield Started(sequence=1, message_id="msg-fail")
        yield Failed(sequence=2, code="rate_limit", message="quota exceeded")

    monkeypatch.setattr(logic, "stream_reply", failing_stream)
    with pytest.raises(RuntimeError, match="rate_limit: quota exceeded"):
        asyncio.run(logic.complete_reply("hi"))
