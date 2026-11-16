"""FastAPI REST + mounted Connect app + native grpc.aio server.

Start with:
  python -m uvicorn backend.app:app --port 8000

REST /docs & /api/chat:             HTTP/1.1 on port 8000
Connect /chat.v1.ChatService/Say:    HTTP/1.1 on port 8000
Native gRPC (HTTP/2):               h2c on port 50051
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from protobuf_to_pydantic import msg_to_pydantic_model

from backend import generated as _generated  # noqa: F401  (import bootstrap)
from chat.v1.chat_pb2 import SayRequest as SayRequestPb, SayResponse as SayResponsePb
from chat.v1.chat_pb2_grpc import add_ChatServiceServicer_to_server
from chat.v1.chat_connect import ChatServiceASGIApplication
from backend.logic import generate_reply
from backend.service import ConnectChatService, GrpcChatService

# Pydantic models are dynamically derived from the compiled .proto
# descriptor. This is not a separate handwritten schema.
SayRequestModel = msg_to_pydantic_model(SayRequestPb)
SayResponseModel = msg_to_pydantic_model(SayResponsePb)


@asynccontextmanager
async def lifespan(app: FastAPI):
    grpc_server = grpc.aio.server()
    add_ChatServiceServicer_to_server(GrpcChatService(), grpc_server)
    listen_addr = os.getenv("GRPC_BIND", "127.0.0.1:50051")
    bound = grpc_server.add_insecure_port(listen_addr)
    if bound == 0:
        raise RuntimeError(f"Could not bind native gRPC at {listen_addr}")
    await grpc_server.start()
    print(f"[grpc] native HTTP/2 (h2c) listening at {listen_addr}")
    try:
        yield
    finally:
        await grpc_server.stop(grace=2.0)


app = FastAPI(
    title="Protobuf + Buf: AI Chat Demo",
    version="1.0.0",
    description=(
        "A single .proto contract powers FastAPI/Pydantic REST, "
        "ConnectRPC, native gRPC, and generated Vue TypeScript clients."
    ),
    lifespan=lifespan,
)

# Vite's proxy means CORS isn't needed for local Vue development, but
# localhost-only CORS is useful for direct browser experiments.
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


@app.post(
    "/api/chat",
    tags=["Chat"],
    operation_id="sendChat",
    response_model=SayResponseModel,
)
async def send_chat(request: SayRequestModel):
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must be nonempty")
    return SayResponseModel(reply=generate_reply(request.text))


# Catch-all must be registered LAST. The generated ASGI application knows
# the canonical Connect path /chat.v1.ChatService/Say. FastAPI's
# REST paths and /docs are matched first.
app.mount("/", ChatServiceASGIApplication(ConnectChatService()))
