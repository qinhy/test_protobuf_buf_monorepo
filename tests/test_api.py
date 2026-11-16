"""Run after `buf generate` and backend dependency installation."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "backend/python/chat/src/chat/v1/chat_pb2.py"
REST_SERVER = ROOT / "backend/python/chat/src/chat/rest/generated/server/application.py"


@pytest.mark.skipif(not GENERATED.exists() or not REST_SERVER.exists(), reason="Run bootstrap.py first")
def test_rest_connect_grpc_use_one_logic():
    import grpc
    from fastapi.testclient import TestClient
    from chat.app import app
    from chat.logic import REPLY
    from chat.v1.chat_pb2 import SayRequest, SayResponse
    from chat.v1.chat_pb2_grpc import ChatServiceStub

    with TestClient(app) as client:
        rest = client.post("/api/chat", json={"text": "rest"})
        assert rest.status_code == 200, rest.text
        assert rest.json()["reply"] == REPLY
        assert client.post("/api/chat", json={"text": "   "}).status_code == 422
        assert client.get("/docs").status_code == 200
        assert "/api/chat" in client.get("/openapi.json").json()["paths"]

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

        with grpc.insecure_channel("127.0.0.1:50051") as channel:
            resp = ChatServiceStub(channel).Say(SayRequest(text="grpc"), timeout=5)
            assert resp.reply == REPLY
