"""The only handwritten REST implementation; no JSON schema or routes here.

The service Protocol, request/response Pydantic models, and FastAPI router are
regenerated from the OpenAPI contract produced by the annotated .proto.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from chat.logic import generate_reply
from chat.rest.generated import models
from chat.rest.generated.server.services import ChatServiceService


class ChatService(ChatServiceService):
    def chat_service_say(self, *, body: Any) -> models.ChatV1SayResponse:
        if not body.text or not body.text.strip():
            raise HTTPException(status_code=422, detail="text must be nonempty")
        return models.ChatV1SayResponse(reply=generate_reply(body.text))
