"""Runtime integration test after `uv run python scripts/generate.py`."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
RPC = ROOT / "src/chat/v1/chat_pb2.py"
ROUTER = ROOT / "src/chat/rest/generated/server/application.py"


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_rest_and_connect_and_grpc():
    import grpc
    from fastapi.testclient import TestClient
    from chat.app import app
    from chat.logic import REPLY
    from chat.v1.chat_pb2 import SayRequest, SayResponse
    from chat.v1.chat_pb2_grpc import ChatServiceStub

    with TestClient(app) as client:
        response = client.post("/api/chat", json={"text": "hi"})
        assert response.status_code == 200, response.text
        assert response.json()["reply"] == REPLY
        assert client.post("/api/chat", json={"text": "   "}).status_code == 422
        connect = client.post(
            "/chat.v1.ChatService/Say", json={"text": "hi"},
            headers={"content-type": "application/json"},
        )
        assert connect.status_code == 200, connect.text
        assert connect.json()["reply"] == REPLY
        binary = client.post(
            "/chat.v1.ChatService/Say",
            content=SayRequest(text="hi").SerializeToString(),
            headers={"content-type": "application/proto", "accept": "application/proto"},
        )
        assert binary.status_code == 200, binary.text
        assert SayResponse.FromString(binary.content).reply == REPLY
        with grpc.insecure_channel("127.0.0.1:50051") as channel:
            assert ChatServiceStub(channel).Say(SayRequest(text="hi"), timeout=5).reply == REPLY
