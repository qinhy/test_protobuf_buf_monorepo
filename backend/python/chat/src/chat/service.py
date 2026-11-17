"""Generated ConnectRPC and native gRPC adapters.

No REST/Connect/gRPC handler contains independent chat logic.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing

from connectrpc.request import RequestContext

from chat.logic import complete_reply, stream_reply
from chat.serialization import to_proto
from chat.v1.chat_connect import ChatService
from chat.v1.chat_pb2 import ChatEvent, SayRequest, SayResponse
from chat.v1.chat_pb2_grpc import ChatServiceServicer


class ChatConnectService(ChatService):
    """ConnectRPC unary and server-streaming service implementation."""

    async def say(
        self, request: SayRequest, ctx: RequestContext[SayRequest, SayResponse]
    ) -> SayResponse:
        return SayResponse(reply=await complete_reply(request.text))

    async def stream_say(
        self, request: SayRequest, ctx: RequestContext[SayRequest, ChatEvent]
    ) -> AsyncIterator[ChatEvent]:
        async with aclosing(stream_reply(request.text)) as events:
            async for event in events:
                yield to_proto(event)


class ChatGrpcService(ChatServiceServicer):
    """Native HTTP/2 gRPC unary and server-streaming service implementation."""

    async def Say(self, request: SayRequest, context) -> SayResponse:
        return SayResponse(reply=await complete_reply(request.text))

    async def StreamSay(self, request: SayRequest, context) -> AsyncIterator[ChatEvent]:
        async with aclosing(stream_reply(request.text)) as events:
            async for event in events:
                yield to_proto(event)


# Backwards-compatible aliases for any external imports.
ConnectChatService = ChatConnectService
GrpcChatService = ChatGrpcService
