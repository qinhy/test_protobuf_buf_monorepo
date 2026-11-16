"""Smoke-test a running backend without importing monorepo root scripts."""
from __future__ import annotations

import asyncio
import grpc
import httpx
from chat.logic import REPLY
from chat.v1.chat_pb2 import SayRequest, SayResponse
from chat.v1.chat_pb2_grpc import ChatServiceStub


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as http:
        rest = await http.post("/api/chat", json={"text": "rest"})
        rest.raise_for_status()
        assert rest.json()["reply"] == REPLY
        print("[PASS] REST")

        connect = await http.post(
            "/chat.v1.ChatService/Say", json={"text": "connect-json"},
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

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        rpc = await ChatServiceStub(channel).Say(SayRequest(text="grpc"), timeout=5)
        assert rpc.reply == REPLY
        print("[PASS] native gRPC")


if __name__ == "__main__":
    asyncio.run(main())
