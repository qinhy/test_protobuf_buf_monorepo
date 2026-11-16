from backend.logic import REPLY, generate_reply


def test_constant_reply():
    assert generate_reply("hello") == REPLY
    assert generate_reply("another input") == REPLY


def test_no_schema_mirror():
    from pathlib import Path
    proto = (Path(__file__).parent.parent / "proto/chat/v1/chat.proto").read_text()
    assert "service ChatService" in proto
    assert "rpc Say(SayRequest) returns (SayResponse)" in proto
