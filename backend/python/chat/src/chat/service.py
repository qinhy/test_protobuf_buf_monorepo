"""Generated Connect interface adapter and native gRPC adapter.

No REST/Connect/gRPC handler contains independent chat logic.
"""
from __future__ import annotations

from chat.logic import generate_reply
from chat.v1.chat_pb2 import SayResponse, SayRequest
from chat.v1.chat_pb2_grpc import ChatServiceServicer
from chat.v1.chat_connect import ChatService
from connectrpc.request import RequestContext


class ConnectChatService(ChatService):
    async def say(
        self, request: SayRequest, ctx: RequestContext
    ) -> SayResponse:
        return SayResponse(reply=generate_reply(request.text))


class GrpcChatService(ChatServiceServicer):
    async def Say(self, request: SayRequest, context) -> SayResponse:
        return SayResponse(reply=generate_reply(request.text))
