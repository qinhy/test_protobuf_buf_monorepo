# chat-backend (C++) — independent CMake + vcpkg project

This directory is a standalone C++20 **CMake** implementation of `ChatService`,
matching the Python and Rust backends' REST, ConnectRPC (JSON and binary
Protobuf), and native gRPC endpoints from the shared `.proto` contract.

## Quick start (Windows PowerShell with Visual Studio 2022)

From any PowerShell prompt (using the `Visual Studio 17 2022` generator + VS 2022's bundled `vcpkg`):

```powershell
cd backend/cpp/chat
cmake --preset windows-vcpkg
cmake --build --preset windows-vcpkg
ctest --preset windows-vcpkg
.\build\Release\chat-server.exe
```

(Or use the `windows-ninja-vcpkg` preset from an **x64 Native Tools Command Prompt for VS 2022**.)

By default:
- REST `/api/chat`, `/api/chat/stream` (NDJSON), `/api/health`, `/openapi.json`, `/docs`: HTTP/1.1 on `127.0.0.1:8000`
- ConnectRPC `/chat.v1.ChatService/Say`, `/chat.v1.ChatService/StreamSay`: HTTP/1.1 on `127.0.0.1:8000`
- Native gRPC: HTTP/2 (`h2c`) on `127.0.0.1:50051`

Configuration environment variables (matching `backend/python/chat` and `backend/rust/chat`):
- `HOST` (default `127.0.0.1`)
- `PORT` (default `8000`)
- `GRPC_BIND` (default `127.0.0.1:50051`)
- `CHAT_PROTO_DIR`: path to the Buf schema module root containing `chat/v1/chat.proto` (defaults to `../../../proto/chat`).

## How code generation works

`CMakeLists.txt` runs `protoc` + `grpc_cpp_plugin` from `vcpkg` (`protobuf` +
`grpc`) during the build:

1. Compiles `chat/v1/chat.proto` (resolving `google/api/annotations.proto` from `proto_deps/`) into `build/generated/chat/v1/chat.pb.{h,cc}` and `chat.grpc.pb.{h,cc}`.
2. Compiles `google/api/http.proto` and `google/api/annotations.proto` into `build/generated/google/api/*.pb.{h,cc}`.
3. Uses `google::protobuf::util::JsonStringToMessage` / `MessageToJsonString` directly on the generated `SayRequest` and `SayResponse` types across REST and ConnectRPC JSON (no manual DTOs).
4. Reads the `(google.api.http)` option (`POST /api/chat`) and ConnectRPC path (`/chat.v1.ChatService/Say`) directly from the generated protobuf descriptors at startup.
5. Embeds `gen/openapi/rest/chat/v1/chat.openapi.json` if present and matching (or synthesizes OpenAPI 3.1 JSON from the descriptor otherwise) and serves it at `/openapi.json` and `/docs`.

## Testing against the monorepo smoke script

With `.\build\Release\chat-server.exe` running in `backend/cpp/chat`, from the
repository root run:

```powershell
uv run python -m scripts.smoke
```
