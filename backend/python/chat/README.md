# chat-backend — independent uv project

This directory is a complete Python **uv project**. The application, generated
RPC code, and generated REST models/routes all live inside its `src/chat/`
package. The monorepo root's `pyproject.toml` and scripts are **not needed** to
run, test, or generate this Python project.

## From this directory (Windows PowerShell)

```powershell
cd backend/python/chat
uv sync
uv run python scripts/bootstrap.py   # FIRST TIME: update Buf deps and generate Python backend
uv run pytest -q
uv run chat-server  # or: uv run uvicorn chat.app:app --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs. Native gRPC uses port 50051.

For ordinary regeneration after modifying the Protobuf schema:

```powershell
uv run python scripts/generate.py
```

To test a running backend from another terminal (in this directory):

```powershell
uv run python scripts/smoke.py
```

## Generator inputs and ownership

- Protobuf schema: `../../../proto/chat/` when inside the monorepo.
- To use a **separately checked-out schema repository** later, set
  `CHAT_PROTO_DIR` to the Buf module directory containing `buf.yaml`.
- Requires the Buf CLI on `PATH` (`BUF_BIN` can override it). Within the
  monorepo, also detects Buf installed via the Vue project's `npm install`.
- `buf.gen.yaml` is **local** to this Python project. Its paths are relative
  to this project: Buf generates straight to `src/` and `.generated/openapi/`.
- `datamodel-code-generator` (in this project's dev dependencies) generates
  `src/chat/rest/generated/models.py` and `server/` from OpenAPI.
- Only generator-owned files are cleaned; handwritten code remains untouched.

The generator does **not** use the root `scripts/`, root `pyproject.toml`, or
any manual copying of generated modules. After splitting repositories,
install the Buf CLI and provide a versioned schema checkout using
`CHAT_PROTO_DIR`. The server still needs generated code before it can start.

## Generated versus handwritten

| Path | Ownership |
|---|---|
| `src/chat/app.py`, `events.py`, `grpc_server.py`, `logic.py`, `serialization.py`, `service.py`, `rest/services/` | Handwritten |
| `src/chat/v1/` | Generated Protobuf, gRPC, ConnectRPC |
| `src/chat/rest/generated/models.py` | Generated Pydantic v2 |
| `src/chat/rest/generated/server/` | Generated FastAPI router |
| `src/chat/rest/generated/services/` | Generated disposable stub scaffolds (ignored) |
| `.generated/openapi/rest/` | Backend-local generated OpenAPI (ignored) |

`verify.py` checks required generated files before packaging or release.
