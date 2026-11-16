"""End-to-end smoke test for REST, Connect JSON, Connect binary and gRPC.

Run while the backend is serving on ports 8000 and 50051.
"""
from __future__ import annotations

import asyncio
import sys

import grpc
import httpx

from chat.logic import REPLY
from chat.v1.chat_pb2 import SayRequest, SayResponse
from chat.v1.chat_pb2_grpc import ChatServiceStub


async def main():
    base = "http://127.0.0.1:8000"
    async with httpx.AsyncClient(base_url=base, timeout=10) as http:
        r = await http.post("/api/chat", json={"text": "hello via REST"})
        r.raise_for_status()
        assert r.json()["reply"] == REPLY, r.text
        print("[PASS] REST JSON /api/chat")

        r = await http.post(
            "/chat.v1.ChatService/Say",
            json={"text": "hello via Connect JSON"},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        assert r.json()["reply"] == REPLY, r.text
        print("[PASS] ConnectRPC ProtoJSON /chat.v1.ChatService/Say")

        r = await http.post(
            "/chat.v1.ChatService/Say",
            content=SayRequest(text="hello via Connect binary").SerializeToString(),
            headers={"Content-Type": "application/proto", "Accept": "application/proto"},
        )
        r.raise_for_status()
        assert SayResponse.FromString(r.content).reply == REPLY
        print("[PASS] ConnectRPC binary Protobuf")

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = ChatServiceStub(channel)
        result = await stub.Say(SayRequest(text="hello via native gRPC"))
        assert result.reply == REPLY
        print("[PASS] native gRPC h2c :50051")

    print("All four API variants returned the same reply.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
