import asyncio

from chat.events import Completed, Delta, Started
from chat.logic import REPLY, complete_reply, generate_reply, stream_reply
from scripts.generate import PROTO


def test_reply_is_shared():
    assert generate_reply("hello") == REPLY
    assert generate_reply("other") == REPLY
    assert asyncio.run(complete_reply("hello")) == REPLY


def test_stream_reply_shares_reply():
    async def collect():
        return [ev async for ev in stream_reply("hello", delay_seconds=0.0)]

    events = asyncio.run(collect())
    assert isinstance(events[0], Started)
    assert "".join(e.text for e in events if isinstance(e, Delta)) == REPLY
    assert isinstance(events[-1], Completed)
    assert events[-1].reply == REPLY


def test_proto_defines_service():
    proto = (PROTO / "chat/v1/chat.proto").read_text()
    assert "service ChatService" in proto
    assert "rpc Say(SayRequest) returns (SayResponse)" in proto
    assert "rpc StreamSay(SayRequest) returns (stream ChatEvent)" in proto
