"""Generated FastAPI REST router + Connect ASGI + native grpc.aio server.

Run: uv run uvicorn chat.app:app --host 127.0.0.1 --port 8000
REST /docs and /api/chat:          HTTP/1.1 on port 8000
Connect /chat.v1.ChatService/Say: HTTP/1.1 on port 8000
Native gRPC:                     HTTP/2 h2c on port 50051
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat.rest.generated.server import create_app
from chat.rest.services.chat_service import ChatService
from chat.service import ConnectChatService, GrpcChatService
from chat.v1.chat_pb2_grpc import add_ChatServiceServicer_to_server
from chat.v1.chat_connect import ChatServiceASGIApplication


@asynccontextmanager
async def lifespan(app: FastAPI):
    grpc_server = grpc.aio.server()
    add_ChatServiceServicer_to_server(GrpcChatService(), grpc_server)
    listen_addr = os.getenv("GRPC_BIND", "127.0.0.1:50051")
    if grpc_server.add_insecure_port(listen_addr) == 0:
        raise RuntimeError(f"Could not bind native gRPC at {listen_addr}")
    await grpc_server.start()
    print(f"[grpc] native HTTP/2 (h2c) listening at {listen_addr}")
    try:
        yield
    finally:
        await grpc_server.stop(grace=2.0)


# create_app generates and registers /api/chat from OpenAPI; no handwritten
# REST handler or FastAPI route decorators are needed.
app = create_app(chat_service=ChatService(), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Health"], operation_id="getHealth")
async def health():
    return {"status": "ok"}


# Mounted LAST so REST /docs and /api/chat win before Connect's catch-all.
app.mount("/", ChatServiceASGIApplication(ConnectChatService()))
