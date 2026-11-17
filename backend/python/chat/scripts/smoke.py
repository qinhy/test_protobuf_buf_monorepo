"""Smoke-test a running backend without importing monorepo root scripts."""
from __future__ import annotations

import asyncio
import json

import grpc
import httpx

from chat.logic import REPLY
from chat.v1.chat_connect import ChatServiceClient
from chat.v1.chat_pb2 import SayRequest, SayResponse
from chat.v1.chat_pb2_grpc import ChatServiceStub


async def main() -> None:
    base = "http://127.0.0.1:8000"
    async with httpx.AsyncClient(base_url=base, timeout=15) as http:
        rest = await http.post("/api/chat", json={"text": "rest"})
        rest.raise_for_status()
        assert rest.json()["reply"] == REPLY
        print("[PASS] REST")

        connect = await http.post(
            "/chat.v1.ChatService/Say",
            json={"text": "connect-json"},
            headers={"content-type": "application/json"},
        )
        connect.raise_for_status()
        assert connect.json()["reply"] == REPLY
        print("[PASS] Connect JSON")

        binary = await http.post(
            "/chat.v1.ChatService/Say",
            content=SayRequest(text="connect-binary").SerializeToString(),
            headers={"content-type": "application/proto", "accept": "application/proto"},
        )
        binary.raise_for_status()
        assert SayResponse.FromString(binary.content).reply == REPLY
        print("[PASS] Connect binary")

        async with http.stream(
            "POST",
            "/api/chat/stream",
            json={"text": "rest-stream"},
            headers={"Accept": "application/x-ndjson"},
        ) as resp:
            resp.raise_for_status()
            assert resp.headers["content-type"].startswith("application/x-ndjson")
            events = [json.loads(line)["result"] async for line in resp.aiter_lines() if line.strip()]
        assert "".join(e["delta"]["text"] for e in events if "delta" in e) == REPLY
        assert events[-1]["complete"]["reply"] == REPLY
        print("[PASS] REST NDJSON stream")

    async with ChatServiceClient(base, send_compression=None, timeout_ms=15000) as client:
        c_events = [e async for e in client.stream_say(SayRequest(text="connect-stream"))]
    assert "".join(e.delta.text for e in c_events if e.WhichOneof("payload") == "delta") == REPLY
    assert c_events[-1].complete.reply == REPLY
    print("[PASS] ConnectRPC stream")

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = ChatServiceStub(channel)
        rpc = await stub.Say(SayRequest(text="grpc"), timeout=5)
        assert rpc.reply == REPLY
        print("[PASS] native gRPC")

        g_events = [e async for e in stub.StreamSay(SayRequest(text="grpc-stream"), timeout=10)]
        assert "".join(e.delta.text for e in g_events if e.WhichOneof("payload") == "delta") == REPLY
        assert g_events[-1].complete.reply == REPLY
        print("[PASS] native gRPC stream")


if __name__ == "__main__":
    asyncio.run(main())
