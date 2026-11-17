# chat-backend (Rust) — independent Cargo project

This directory is a standalone Rust **Cargo** implementation of `ChatService`,
matching the Python backend's REST, ConnectRPC (JSON and binary Protobuf), and
native gRPC endpoints from the single shared `.proto` contract.

## Quick start (Windows PowerShell)

```powershell
cd backend/rust/chat
cargo test
cargo run
```

By default:
- REST `/api/chat`, `/api/chat/stream` (NDJSON), `/api/health`, `/openapi.json`, `/docs`: HTTP/1.1 on `127.0.0.1:8000`
- ConnectRPC `/chat.v1.ChatService/Say`, `/chat.v1.ChatService/StreamSay`: HTTP/1.1 on `127.0.0.1:8000`
- Native gRPC: HTTP/2 (`h2c`) on `127.0.0.1:50051`

Configuration environment variables (matching `backend/python/chat`):
- `HOST` (default `127.0.0.1`)
- `PORT` (default `8000`)
- `GRPC_BIND` (default `127.0.0.1:50051`)
- `CHAT_PROTO_DIR`: path to the Buf schema module root containing `chat/v1/chat.proto` (defaults to `../../../proto/chat`).

## How code generation works

`build.rs` uses pure-Rust [`protox`](https://crates.io/crates/protox) +
[`tonic-prost-build`](https://crates.io/crates/tonic-prost-build) so no external
`protoc` binary is required:

1. Compiles `chat/v1/chat.proto` (resolving `google/api/annotations.proto` from `proto_deps/`).
2. Generates Prost message types (`SayRequest`, `SayResponse`) with `serde::{Serialize, Deserialize}` derives and Tonic gRPC server/client stubs.
3. Extracts the `(google.api.http)` binding (`POST /api/chat`) and ConnectRPC path (`/chat.v1.ChatService/Say`) directly from the compiled `FileDescriptorSet`.
4. Loads the Buf-generated OpenAPI 3.1 document from `gen/openapi/rest/chat/v1/chat.openapi.json` if present (or synthesizes one from the descriptor otherwise) and serves it at `/openapi.json` and `/docs`.

## Testing against the monorepo smoke script

With `cargo run` active in `backend/rust/chat`, from the repository root run:

```powershell
uv run python -m scripts.smoke
```
