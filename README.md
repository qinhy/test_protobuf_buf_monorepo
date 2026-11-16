# Protobuf + Buf: FastAPI / Vue / ConnectRPC / gRPC chat demo

A deliberately tiny, schema-first app. **`proto/chat/v1/chat.proto` is the only handwritten API schema.**
Every protocol returns the same fixed text through `backend/logic.py`.

## Capabilities

| Interface | Endpoint | Implementation | Payload |
|---|---|---|---|
| REST | `POST http://127.0.0.1:8000/api/chat` | FastAPI + generated Pydantic models | JSON |
| Connect JSON | `POST http://127.0.0.1:8000/chat.v1.ChatService/Say` | Connect Python ASGI | ProtoJSON |
| Connect binary | Same Connect endpoint | Connect Python ASGI | Protobuf binary |
| Native gRPC | `127.0.0.1:50051`, `chat.v1.ChatService/Say` | grpc.aio | Protobuf over HTTP/2 (h2c) |
| Vue | `http://127.0.0.1:5173` | Vite + generated TypeScript clients | Pick REST/Connect JSON/Connect binary |

All four backends call `generate_reply(text)`; there are **no independent response implementations**.
FastAPI serves REST and mounts the generated Connect ASGI app on port 8000. A `grpc.aio`
server starts on port 50051 in the same FastAPI lifespan. This ensures native gRPC actually
works with an HTTP/2 implementation rather than depending on Uvicorn's HTTP/2 trailers.

## Prerequisites

- Python **3.11+**, `pip`
- Node.js **22+**, npm
- [Buf CLI](https://buf.build/docs/installation/) on `PATH`
- Internet access for first-time `pip`, `npm`, and Buf remote plugin downloads

No Go, Java, standalone `protoc`, or database required.

## Quick start (macOS / Linux / Windows PowerShell)

From the repo root:

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python scripts/bootstrap.py
```

`bootstrap.py` runs `buf lint`, `buf generate`, exports FastAPI's REST OpenAPI,
installs the frontend, and generates its typed REST client.

**Terminal 1 (backend):**

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

**Terminal 2 (Vue frontend):**

```bash
cd frontend
npm run dev
```

Now visit http://127.0.0.1:5173 and switch between REST JSON, Connect JSON,
and Connect Protobuf. The same text should appear each time.

Swagger UI: http://127.0.0.1:8000/docs

## Automated checks

```bash
python -m pytest tests -q
```

Before generation the pure logic tests run; after generation the API integration test also exercises REST, Connect JSON/binary and gRPC. Stop a separately running backend before executing that test (it binds gRPC port 50051).

## Protocol smoke tests

With the backend running, in another terminal from the repo root:

```bash
python -m scripts.smoke
```

Or manually try each protocol:

**REST JSON**

```bash
curl -sS http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello REST"}'
```

**ConnectRPC JSON** (note the different endpoint)

```bash
curl -sS http://127.0.0.1:8000/chat.v1.ChatService/Say \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Connect"}'
```

**Native gRPC** (using the optional [grpcurl](https://github.com/fullstorydev/grpcurl) tool):

```bash
grpcurl -plaintext -import-path proto -proto chat/v1/chat.proto \
  -d '{"text":"Hello gRPC"}' \
  127.0.0.1:50051 chat.v1.ChatService/Say
```

The `scripts/smoke.py` test also sends raw binary Protobuf via ConnectRPC.
Note: gRPC uses **h2c (HTTP/2 without TLS)** for this *local-only* test.
Put it behind TLS/authentication before exposing it to a network.

## How code generation works

```text
proto/chat/v1/chat.proto                      SINGLE SOURCE OF TRUTH
   ├── Buf / protocolbuffers/python ──> gen/python/chat/v1/chat_pb2.py
   ├── Buf / grpc/python ────────────> gen/python/chat/v1/chat_pb2_grpc.py
   ├── Buf / connectrpc/py ──────────> gen/python/chat/v1/chat_connect.py
   ├── Buf / bufbuild/es ────────────> frontend/src/gen/chat/v1/chat_pb.ts
   └── Buf / connect-openapi ────────> schema/connect/...openapi.yaml
              │
              └─ descriptor -> protobuf-to-pydantic (runtime)
                           └─ FastAPI REST /api/chat
                                 └─ schema/openapi.rest.json
                                       └─ Hey API -> frontend/src/gen/rest/
```

**Important distinction:** `schema/connect/` documents the ConnectRPC HTTP endpoint.
`schema/openapi.rest.json` documents FastAPI's real REST endpoint `/api/chat`.
Both are generated from the *same* `.proto` messages, but they are not interchangeable
API specs and do not require maintaining two handwritten schemas.

## Relevant handwritten files

- `proto/chat/v1/chat.proto` — canonical interface and models
- `buf.yaml`, `buf.gen.yaml` — schema validation/codegen
- `backend/logic.py` — one chat implementation
- `backend/app.py` — FastAPI REST, Pydantic models and service mounting
- `backend/service.py` — generated Connect interface + grpcio adapters
- `frontend/src/App.vue` — minimal chat UI
- `frontend/src/api.ts` — only switches between **generated** REST and Connect clients
- `scripts/smoke.py` — REST, Connect JSON, Connect binary, native gRPC smoke tests
- `tests/test_logic.py` — pure-Python unit tests

### Regeneration after schema changes

```bash
python scripts/bootstrap.py
```

If adding new Protobuf fields, the REST Pydantic models automatically follow generated
descriptors. Then FastAPI OpenAPI and the generated Vue REST/Connect clients are refreshed.

## Limitations and future extensions

- This intentionally implements **one unary RPC**. It does not implement model inference,
  persistent conversations, authentication, client streaming or browser bidirectional streaming.
- Connect for Python is **beta**. The Buf remote plugins need connectivity during generation.
- The demo's Google Protobuf compatibility setting (`protobuf=google`) is required because
  `protobuf-to-pydantic` reads Google Protobuf descriptors.
- `protobuf-to-pydantic` generates Pydantic models dynamically here; this keeps the schema
  canonical, but static Python type checkers see a runtime-created model type.
- `http://127.0.0.1:8000/docs` describes **REST**; it does not present native gRPC.
- Connect browser client `fetch` supports unary and server streaming, but not browser
  full-duplex client/bidirectional streaming. RSocket/WebSocket is a future separate adapter.
- The generated gRPC API runs **on port 50051**, independently of the Connect ASGI mount;
  that avoids relying on Uvicorn for native gRPC/HTTP2 support.
- Generated directories are excluded from source control here. Run bootstrap after cloning.

## External documentation

- [Buf generation](https://buf.build/docs/generate/)
- [Connect for Python](https://connectrpc.com/docs/python/getting-started/)
- [Connect browser](https://connectrpc.com/docs/web/getting-started/)
- [protobuf-to-pydantic](https://github.com/so1n/protobuf_to_pydantic)
- [Hey API](https://heyapi.dev/docs/openapi/typescript/get-started)
