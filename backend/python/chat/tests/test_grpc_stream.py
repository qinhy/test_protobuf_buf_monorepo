"""Native grpc.aio server-streaming and cross-protocol parity tests."""
from __future__ import annotations

import asyncio
import json
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


def _normalize_proto_event(event) -> tuple[int, str, str]:
    kind = event.WhichOneof("payload")
    if kind == "start":
        return (event.sequence, "start", "")
    if kind == "delta":
        return (event.sequence, "delta", event.delta.text)
    if kind == "complete":
        return (event.sequence, "complete", event.complete.reply)
    if kind == "failure":
        return (event.sequence, "failure", f"{event.failure.code}:{event.failure.message}")
    raise AssertionError(f"Unknown payload: {kind}")


def _normalize_ndjson_event(event: dict) -> tuple[int, str, str]:
    seq = event["sequence"]
    if "start" in event:
        return (seq, "start", "")
    if "delta" in event:
        return (seq, "delta", event["delta"]["text"])
    if "complete" in event:
        return (seq, "complete", event["complete"]["reply"])
    if "failure" in event:
        return (seq, "failure", f"{event['failure']['code']}:{event['failure']['message']}")
    raise AssertionError(f"Unknown NDJSON event: {event}")


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_cross_protocol_streaming_parity(monkeypatch):
    from fastapi.testclient import TestClient
    import grpc

    from chat.app import app
    from chat.logic import REPLY
    from chat.v1.chat_pb2 import ChatEvent, SayRequest
    from chat.v1.chat_pb2_grpc import ChatServiceStub

    grpc_addr = f"127.0.0.1:{_free_port()}"
    monkeypatch.setenv("GRPC_BIND", grpc_addr)

    with TestClient(app) as client:
        with client.stream("POST", "/api/chat/stream", json={"text": "parity"}) as rest_res:
            assert rest_res.status_code == 200
            rest_events = [
                _normalize_ndjson_event(json.loads(line)["result"])
                for line in rest_res.iter_lines()
                if line.strip()
            ]

        connect_res = client.post(
            "/chat.v1.ChatService/StreamSay",
            content=_encode_connect_frame(0, SayRequest(text="parity").SerializeToString()),
            headers={"Content-Type": "application/connect+proto"},
        )
        assert connect_res.status_code == 200
        connect_frames = _decode_connect_frames(connect_res.content)
        connect_events = [
            _normalize_proto_event(ChatEvent.FromString(payload))
            for flags, payload in connect_frames[:-1]
            if flags == 0
        ]

        async def call_grpc_stream():
            async with grpc.aio.insecure_channel(grpc_addr) as channel:
                stub = ChatServiceStub(channel)
                return [
                    _normalize_proto_event(ev)
                    async for ev in stub.StreamSay(SayRequest(text="parity"), timeout=10)
                ]

        grpc_events = asyncio.run(call_grpc_stream())

    assert rest_events == connect_events == grpc_events
    assert rest_events[0][1] == "start"
    assert rest_events[-1] == (len(rest_events), "complete", REPLY)
