# chat-rpc-client — independent Python native RPC frontend

Self-contained Python **uv project** demonstrating a pure API consumer calling
`chat.v1.ChatService/Say` over **native gRPC** (`:50051`) as well as
**ConnectRPC** (`connect-binary`, `connect-json`, and `grpc-web` on `:8000`).

It generates its own client stubs directly from `proto/chat` (`chat/v1/chat.proto`)
and does **not** import anything from `backend/python/chat`.

## From this directory (Windows PowerShell)

```powershell
cd frontend/python/chat-rpc
uv sync
uv run python scripts/generate.py   # or bootstrap.py on first setup
uv run pytest -q
uv run chat-rpc-demo
```

Examples while `chat-server` is running:

```powershell
uv run chat-rpc-demo --transport grpc --text "Hello native gRPC"
uv run chat-rpc-demo --stream --transport all --text "Hello all streaming RPC transports"
uv run chat-rpc-demo --transport all --text "Hello all RPC transports"
uv run chat-rpc-demo --interactive
```

## Generated versus handwritten

| Path | Ownership |
|---|---|
| `src/chat_rpc/` | Handwritten RPC demo client & CLI |
| `src/chat/v1/` | Generated Protobuf, gRPC, and ConnectRPC client stubs |

Set `CHAT_PROTO_DIR` to a separate schema repository's Buf module root when
splitting repositories.
