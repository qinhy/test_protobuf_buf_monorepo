"""Cancellation tests ensuring backend generators stop on disconnect/cancel."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RPC = ROOT / "src/chat/v1/chat_pb2.py"
ROUTER = ROOT / "src/chat/rest/generated/server/application.py"


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_rest_stream_stops_when_request_disconnects(monkeypatch):
    from starlette.requests import Request

    from chat.events import Delta, Started
    from chat.rest.services import chat as rest_chat

    yielded: list[int] = []
    closed = asyncio.Event()

    async def fake_stream(text: str, **kwargs):
        _ = text, kwargs
        try:
            yielded.append(1)
            yield Started(sequence=1, message_id="msg-cancel")
            for seq in range(2, 20):
                yielded.append(seq)
                yield Delta(sequence=seq, text="chunk ")
                await asyncio.sleep(0.01)
        finally:
            closed.set()

    monkeypatch.setattr(rest_chat, "stream_reply", fake_stream)

    async def exercise():
        checks = 0

        class FakeRequest:
            async def is_disconnected(self) -> bool:
                nonlocal checks
                checks += 1
                return checks >= 3

        class FakeBody:
            text = "cancel me"

        svc = rest_chat.ChatRestService()
        response = await svc.stream_say(request=FakeRequest(), body=FakeBody())  # type: ignore[arg-type]
        chunks = [chunk async for chunk in response.body_iterator]
        assert len(chunks) == 2
        assert closed.is_set()
        assert len(yielded) < 10

    _ = Request
    asyncio.run(exercise())


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_grpc_and_connect_generators_close_cleanly_on_aclose(monkeypatch):
    from chat import service
    from chat.events import Delta, Started
    from chat.v1.chat_pb2 import SayRequest

    closed = asyncio.Event()

    async def fake_stream(text: str, **kwargs):
        _ = text, kwargs
        try:
            yield Started(sequence=1, message_id="msg-aclose")
            for seq in range(2, 20):
                yield Delta(sequence=seq, text="x")
                await asyncio.sleep(0.01)
        finally:
            closed.set()

    monkeypatch.setattr(service, "stream_reply", fake_stream)

    async def exercise():
        connect_gen = service.ChatConnectService().stream_say(SayRequest(text="hi"), None)  # type: ignore[arg-type]
        first = await anext(connect_gen)
        assert first.sequence == 1
        await connect_gen.aclose()
        assert closed.is_set()

        closed.clear()
        grpc_gen = service.ChatGrpcService().StreamSay(SayRequest(text="hi"), None)
        first_grpc = await anext(grpc_gen)
        assert first_grpc.sequence == 1
        await grpc_gen.aclose()
        assert closed.is_set()

    asyncio.run(exercise())
