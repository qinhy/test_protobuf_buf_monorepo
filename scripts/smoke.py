"""End-to-end smoke test for unary & streaming REST, ConnectRPC, and native gRPC.

Run while the backend is serving on ports 8000 and 50051.
"""
from __future__ import annotations

import asyncio
import json
import sys

import grpc
import httpx

from chat.logic import REPLY
from chat.v1.chat_connect import ChatServiceClient
from chat.v1.chat_pb2 import SayRequest, SayResponse
from chat.v1.chat_pb2_grpc import ChatServiceStub


async def main() -> None:
    base = "http://127.0.0.1:8000"
    async with httpx.AsyncClient(base_url=base, timeout=15) as http:
        # 1. Unary REST
        r = await http.post("/api/chat", json={"text": "hello via REST"})
        r.raise_for_status()
        assert r.json()["reply"] == REPLY, r.text
        print("[PASS] REST JSON /api/chat")

        # 2. Unary Connect JSON
        r = await http.post(
            "/chat.v1.ChatService/Say",
            json={"text": "hello via Connect JSON"},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        assert r.json()["reply"] == REPLY, r.text
        print("[PASS] ConnectRPC ProtoJSON /chat.v1.ChatService/Say")

        # 3. Unary Connect binary
        r = await http.post(
            "/chat.v1.ChatService/Say",
            content=SayRequest(text="hello via Connect binary").SerializeToString(),
            headers={"Content-Type": "application/proto", "Accept": "application/proto"},
        )
        r.raise_for_status()
        assert SayResponse.FromString(r.content).reply == REPLY
        print("[PASS] ConnectRPC binary Protobuf /chat.v1.ChatService/Say")

        # 4. Streaming REST NDJSON
        async with http.stream(
            "POST",
            "/api/chat/stream",
            json={"text": "hello via REST stream"},
            headers={"Accept": "application/x-ndjson"},
        ) as resp:
            resp.raise_for_status()
            assert resp.headers["content-type"].startswith("application/x-ndjson")
            events = [json.loads(line)["result"] async for line in resp.aiter_lines() if line.strip()]
        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        assert "start" in events[0]
        assert "".join(e["delta"]["text"] for e in events if "delta" in e) == REPLY
        assert events[-1]["complete"]["reply"] == REPLY
        print("[PASS] REST NDJSON stream /api/chat/stream")

    # 5. Streaming ConnectRPC binary via generated ChatServiceClient
    async with ChatServiceClient(base, send_compression=None, timeout_ms=15000) as connect_client:
        connect_events = [
            event async for event in connect_client.stream_say(SayRequest(text="hello via Connect stream"))
        ]
    assert [e.sequence for e in connect_events] == list(range(1, len(connect_events) + 1))
    assert connect_events[0].WhichOneof("payload") == "start"
    assert "".join(
        e.delta.text for e in connect_events if e.WhichOneof("payload") == "delta"
    ) == REPLY
    assert connect_events[-1].complete.reply == REPLY
    print("[PASS] ConnectRPC stream /chat.v1.ChatService/StreamSay")

    # 6. Unary + Streaming native gRPC
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = ChatServiceStub(channel)
        result = await stub.Say(SayRequest(text="hello via native gRPC"))
        assert result.reply == REPLY
        print("[PASS] native gRPC unary h2c :50051")

        grpc_events = [
            event async for event in stub.StreamSay(SayRequest(text="hello via native gRPC stream"))
        ]
        assert [e.sequence for e in grpc_events] == list(range(1, len(grpc_events) + 1))
        assert grpc_events[0].WhichOneof("payload") == "start"
        assert "".join(
            e.delta.text for e in grpc_events if e.WhichOneof("payload") == "delta"
        ) == REPLY
        assert grpc_events[-1].complete.reply == REPLY
        print("[PASS] native gRPC stream h2c :50051")

    print("All unary and streaming API variants returned the same reply.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
