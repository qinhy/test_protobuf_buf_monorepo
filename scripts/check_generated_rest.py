"""Post-generation check: no server startup or native gRPC port needed.

This verifies the generated FastAPI router, request/response Pydantic models,
service interface, JSON response, and source-derived OpenAPI agree.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from chat.logic import REPLY
from chat.rest.generated.server import create_app
from chat.rest.services.chat_service import ChatService


def main() -> None:
    api = create_app(chat_service=ChatService())
    with TestClient(api) as client:
        response = client.post("/api/chat", json={"text": "Hello generated FastAPI"})
        assert response.status_code == 200, response.text
        assert response.json() == {"reply": REPLY}, response.text
        bad = client.post("/api/chat", json={"text": "   "})
        assert bad.status_code == 422, bad.text
        assert "/api/chat" in client.get("/openapi.json").json()["paths"]
    print("[PASS] generated OpenAPI -> Pydantic -> FastAPI REST service")


if __name__ == "__main__":
    main()
