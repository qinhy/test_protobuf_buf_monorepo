"""ConnectRPC server-streaming ASGI integration tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[1]
RPC = ROOT / "src/chat/v1/chat_pb2.py"
ROUTER = ROOT / "src/chat/rest/generated/server/application.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _encode_connect_frame(flags: int, payload: bytes) -> bytes:
    return bytes([flags]) + len(payload).to_bytes(4, "big") + payload


def _decode_connect_frames(data: bytes) -> list[tuple[int, bytes]]:
    frames: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        flags = data[offset]
        length = int.from_bytes(data[offset + 1 : offset + 5], "big")
        offset += 5
        frames.append((flags, data[offset : offset + length]))
        offset += length
    return frames


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_connect_stream_binary_and_json(monkeypatch):
    from fastapi.testclient import TestClient

    from chat.app import app
    from chat.logic import REPLY
    from chat.v1.chat_pb2 import ChatEvent, SayRequest

    monkeypatch.setenv("GRPC_BIND", f"127.0.0.1:{_free_port()}")
    with TestClient(app) as client:
        req_bytes = SayRequest(text="hello connect stream").SerializeToString()
        res = client.post(
            "/chat.v1.ChatService/StreamSay",
            content=_encode_connect_frame(0, req_bytes),
            headers={"Content-Type": "application/connect+proto"},
        )
        assert res.status_code == 200, res.text
        frames = _decode_connect_frames(res.content)
        assert frames[-1][0] == 0x02
        events = [ChatEvent.FromString(payload) for flags, payload in frames[:-1] if flags == 0]
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert events[0].WhichOneof("payload") == "start"
        assert "".join(
            e.delta.text for e in events if e.WhichOneof("payload") == "delta"
        ) == REPLY
        assert events[-1].complete.reply == REPLY

        json_res = client.post(
            "/chat.v1.ChatService/StreamSay",
            content=_encode_connect_frame(0, b'{"text":"hello connect json stream"}'),
            headers={"Content-Type": "application/connect+json"},
        )
        assert json_res.status_code == 200, json_res.text
        json_frames = _decode_connect_frames(json_res.content)
        assert json_frames[-1][0] == 0x02
        assert len(json_frames) == len(frames)


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_connect_service_async_generator():
    from chat.logic import REPLY
    from chat.service import ChatConnectService
    from chat.v1.chat_pb2 import SayRequest

    async def exercise():
        svc = ChatConnectService()
        events = [ev async for ev in svc.stream_say(SayRequest(text="hi"), None)]  # type: ignore[arg-type]
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert "".join(e.delta.text for e in events if e.WhichOneof("payload") == "delta") == REPLY
        assert events[-1].complete.reply == REPLY

    asyncio.run(exercise())
