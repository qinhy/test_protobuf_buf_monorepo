"""Generated FastAPI REST router + Connect ASGI + native grpc.aio server.

Run: uv run chat-server  # or: uv run uvicorn chat.app:app --host 127.0.0.1 --port 8000
REST /docs, /api/chat, /api/chat/stream: HTTP/1.1 on port 8000
Connect /chat.v1.ChatService/*:          HTTP/1.1 on port 8000
Native gRPC:                             HTTP/2 h2c on port 50051
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from chat.grpc_server import grpc_lifespan
from chat.rest.generated.server import (
    build_router,
    serve_source_openapi,
    validation_error_handler,
)
from chat.rest.services.chat import ChatRestService
from chat.service import ChatConnectService
from chat.v1.chat_connect import ChatServiceASGIApplication

app = FastAPI(title="chat", version="1.0.0", lifespan=grpc_lifespan)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Generated FastAPI REST router (single-service layout).
app.include_router(build_router(service=ChatRestService()))
serve_source_openapi(app)


@app.get("/api/health", tags=["Health"], operation_id="getHealth")
async def health():
    return {"status": "ok"}


# Mounted LAST so REST /docs, /openapi.json, and /api/* win before Connect's catch-all.
app.mount("/", ChatServiceASGIApplication(ChatConnectService()))
