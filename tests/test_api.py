"""Run after `buf generate` and backend dependency installation."""
from pathlib import Path

import pytest

GENERATED = Path(__file__).resolve().parent.parent / "gen/python/chat/v1/chat_pb2.py"


@pytest.mark.skipif(not GENERATED.exists(), reason="Run buf generate first")
def test_rest_connect_grpc_use_one_logic():
    import grpc
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.logic import REPLY
    from backend import generated as _generated  # noqa: F401
    from chat.v1.chat_pb2 import SayRequest, SayResponse
    from chat.v1.chat_pb2_grpc import ChatServiceStub

    with TestClient(app) as client:
        assert client.post("/api/chat", json={"text": "rest"}).json()["reply"] == REPLY

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
