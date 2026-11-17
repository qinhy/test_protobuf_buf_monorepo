"""Native grpc.aio server lifecycle managed via FastAPI lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
import grpc

from chat.service import ChatGrpcService
from chat.v1.chat_pb2_grpc import add_ChatServiceServicer_to_server


@asynccontextmanager
async def grpc_lifespan(app: FastAPI):
    """Start native HTTP/2 gRPC alongside the HTTP ASGI application."""
    _ = app
    server = grpc.aio.server()
    add_ChatServiceServicer_to_server(ChatGrpcService(), server)
    listen_addr = os.getenv("GRPC_BIND", "127.0.0.1:50051")
    if server.add_insecure_port(listen_addr) == 0:
        raise RuntimeError(f"Could not bind native gRPC at {listen_addr}")
    await server.start()
    print(f"[grpc] native HTTP/2 (h2c) listening at {listen_addr}")
    try:
        yield
    finally:
        await server.stop(grace=2.0)
