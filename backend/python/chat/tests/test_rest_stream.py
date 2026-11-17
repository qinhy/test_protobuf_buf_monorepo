"""REST NDJSON streaming, CORS, validation, error envelopes, and real-server timing tests."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import threading
import time

import httpx
import pytest
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
RPC = ROOT / "src/chat/v1/chat_pb2.py"
ROUTER = ROOT / "src/chat/rest/generated/server/application.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_rest_stream_ndjson_cors_and_validation(monkeypatch):
    from fastapi.testclient import TestClient

    from chat.app import app
    from chat.logic import REPLY

    monkeypatch.setenv("GRPC_BIND", f"127.0.0.1:{_free_port()}")
    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"text": "hello"},
            headers={
                "Accept": "application/x-ndjson",
                "Origin": "http://127.0.0.1:5173",
            },
        ) as res:
            assert res.status_code == 200
            assert res.headers["content-type"].startswith("application/x-ndjson")
            assert res.headers["cache-control"] == "no-store"
            assert res.headers["x-accel-buffering"] == "no"
            assert res.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
            events = [json.loads(line)["result"] for line in res.iter_lines() if line.strip()]

        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        assert "start" in events[0] and events[0]["start"]["messageId"]
        assert "".join(e["delta"]["text"] for e in events if "delta" in e) == REPLY
        assert events[-1]["complete"]["reply"] == REPLY

        assert client.post("/api/chat/stream", json={"text": "   "}).status_code == 422
        assert client.post("/api/chat/stream", json={}).status_code == 422


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_rest_stream_error_after_first_event(monkeypatch):
    from fastapi.testclient import TestClient

    from chat.app import app
    from chat.events import Started
    from chat.rest.services import chat as rest_chat

    async def failing_stream(text: str, **kwargs):
        _ = text, kwargs
        yield Started(sequence=1, message_id="msg-err")
        raise RuntimeError("boom after start")

    monkeypatch.setenv("GRPC_BIND", f"127.0.0.1:{_free_port()}")
    monkeypatch.setattr(rest_chat, "stream_reply", failing_stream)

    with TestClient(app) as client:
        with client.stream("POST", "/api/chat/stream", json={"text": "hi"}) as res:
            assert res.status_code == 200
            lines = [json.loads(line) for line in res.iter_lines() if line.strip()]

    assert len(lines) == 2
    assert lines[0]["result"]["start"]["messageId"] == "msg-err"
    assert lines[1]["error"]["code"] == 13
    assert lines[1]["error"]["message"] == "internal error"


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_rest_stream_first_delta_arrives_before_completion(monkeypatch):
    from chat.app import app
    from chat.events import Completed, Delta, Started
    from chat.rest.services import chat as rest_chat

    async def slow_stream(text: str, **kwargs):
        import asyncio

        _ = text, kwargs
        yield Started(sequence=1, message_id="msg-timing")
        await asyncio.sleep(0.02)
        yield Delta(sequence=2, text="first ")
        await asyncio.sleep(0.35)
        yield Delta(sequence=3, text="second")
        yield Completed(sequence=4, reply="first second")

    monkeypatch.setenv("GRPC_BIND", f"127.0.0.1:{_free_port()}")
    monkeypatch.setattr(rest_chat, "stream_reply", slow_stream)

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn failed to start in time"

    try:
        timestamps: list[tuple[float, dict]] = []
        started_at = time.monotonic()
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0) as client:
            with client.stream(
                "POST",
                "/api/chat/stream",
                json={"text": "timing"},
                headers={"Accept": "application/x-ndjson"},
            ) as res:
                assert res.status_code == 200
                for line in res.iter_lines():
                    if line.strip():
                        timestamps.append((time.monotonic() - started_at, json.loads(line)["result"]))

        first_delta_t = next(t for t, ev in timestamps if "delta" in ev)
        complete_t = next(t for t, ev in timestamps if "complete" in ev)
        assert complete_t - first_delta_t >= 0.2
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
