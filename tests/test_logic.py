from chat.logic import REPLY,generate_reply
from scripts.generate import PROTO


def test_reply_is_shared():
    assert generate_reply('hello') == REPLY
    assert generate_reply('other') == REPLY


def test_proto_defines_service():
    proto=(PROTO/'chat/v1/chat.proto').read_text()
    assert 'service ChatService' in proto
    assert 'rpc Say(SayRequest) returns (SayResponse)' in proto
