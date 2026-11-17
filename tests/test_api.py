"""Run after `buf generate` and backend dependency installation."""
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "backend/python/chat/src/chat/v1/chat_pb2.py"
REST_SERVER = ROOT / "backend/python/chat/src/chat/rest/generated/server/application.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(not GENERATED.exists() or not REST_SERVER.exists(), reason="Run bootstrap.py first")
def test_rest_connect_grpc_use_one_logic(monkeypatch):
    import grpc
    from fastapi.testclient import TestClient
    from chat.app import app
    from chat.logic import REPLY
    from chat.v1.chat_pb2 import ChatEvent, SayRequest, SayResponse
    from chat.v1.chat_pb2_grpc import ChatServiceStub

    grpc_addr = f"127.0.0.1:{_free_port()}"
    monkeypatch.setenv("GRPC_BIND", grpc_addr)

    with TestClient(app) as client:
        rest = client.post("/api/chat", json={"text": "rest"})
        assert rest.status_code == 200, rest.text
        assert rest.json()["reply"] == REPLY
        assert client.post("/api/chat", json={"text": "   "}).status_code == 422
        assert client.get("/docs").status_code == 200
        spec = client.get("/openapi.json").json()
        assert "/api/chat" in spec["paths"]
        assert "/api/chat/stream" in spec["paths"]

        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"text": "rest stream"},
            headers={"Accept": "application/x-ndjson"},
        ) as stream_res:
            assert stream_res.status_code == 200, stream_res.text
            events = [json.loads(line)["result"] for line in stream_res.iter_lines() if line.strip()]
        assert "".join(e["delta"]["text"] for e in events if "delta" in e) == REPLY
        assert events[-1]["complete"]["reply"] == REPLY

        res = client.post(
            "/chat.v1.ChatService/Say",
            json={"text": "connect"},
            headers={"content-type": "application/json"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["reply"] == REPLY

        res = client.post(
            "/chat.v1.ChatService/Say",
            content=SayRequest(text="binary").SerializeToString(),
            headers={"content-type": "application/proto", "accept": "application/proto"},
        )
        assert res.status_code == 200, res.text
        assert SayResponse.FromString(res.content).reply == REPLY

        req_bytes = SayRequest(text="stream").SerializeToString()
        frame = bytes([0]) + len(req_bytes).to_bytes(4, "big") + req_bytes
        stream_connect = client.post(
            "/chat.v1.ChatService/StreamSay",
            content=frame,
            headers={"content-type": "application/connect+proto"},
        )
        assert stream_connect.status_code == 200, stream_connect.text
        offset = 0
        connect_events = []
        raw = stream_connect.content
        while offset < len(raw):
            flags = raw[offset]
            length = int.from_bytes(raw[offset + 1 : offset + 5], "big")
            offset += 5
            chunk = raw[offset : offset + length]
            offset += length
            if flags == 0:
                connect_events.append(ChatEvent.FromString(chunk))
        assert "".join(
            e.delta.text for e in connect_events if e.WhichOneof("payload") == "delta"
        ) == REPLY

        with grpc.insecure_channel(grpc_addr) as channel:
            stub = ChatServiceStub(channel)
            resp = stub.Say(SayRequest(text="grpc"), timeout=5)
            assert resp.reply == REPLY
            grpc_events = list(stub.StreamSay(SayRequest(text="grpc stream"), timeout=10))
            assert "".join(
                e.delta.text for e in grpc_events if e.WhichOneof("payload") == "delta"
            ) == REPLY
            assert grpc_events[-1].complete.reply == REPLY
