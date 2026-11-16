"""These tests run from backend/python/chat, without monorepo root imports."""
from chat.logic import REPLY, generate_reply


def test_reply():
    assert generate_reply("hello") == REPLY
    assert generate_reply("another request") == REPLY
