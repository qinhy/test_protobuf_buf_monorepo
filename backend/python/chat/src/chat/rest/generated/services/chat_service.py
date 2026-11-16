"""Implement ChatServiceService of chat.rest.generated.server.services; chat.rest.generated.server.main imports ChatService from this module.

datamodel-code-generator wrote this module once, with a stub for each method, and never overwrites it. Generating the
server again updates the Protocol, so type checkers point at the methods to change.
"""

from __future__ import annotations

from chat.rest.generated import models
from chat.rest.generated.server import HTTPResult
from chat.rest.generated.server.services import ChatServiceService
from fastapi.responses import Response


class ChatService(ChatServiceService):
    """Implement the chat_service operations."""

    def chat_service_say(
        self,
        *,
        body: models.ApiChatPostRequest,
    ) -> models.ChatV1SayResponse | HTTPResult[models.ChatV1SayResponse] | Response:
        """
        Handle POST /api/chat.
        """
        raise NotImplementedError
