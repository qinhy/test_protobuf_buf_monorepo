# Chat API monorepo — independent per-technology projects

Single `.proto` contract → Buf → OpenAPI 3.1 → Pydantic v2 + FastAPI, with
ConnectRPC, native gRPC, and Vue 3 clients. **No manual Protobuf-to-Pydantic
adapter and no generated-file copying.**

## Project layout

```text
proto/
  chat/                         # Independent Buf source project
    buf.yaml                    # Own module/dependencies and buf.lock (on bootstrap)
    chat/v1/chat.proto          # Handwritten, stable import chat/v1/chat.proto
    gen/openapi/                # GENERATED REST + Connect specifications
backend/
  python/
    chat/                       # Independent installable Python application
      pyproject.toml           # Has its OWN dev dependencies and pytest config
      buf.gen.yaml             # Python-only generator; direct targets
      scripts/bootstrap.py     # Python-project-local setup
      scripts/generate.py      # Python-project-local generation
      tests/                   # Tests runnable with local uv run pytest
      README.md
      verify.py
      src/chat/
        app.py                  # Handwritten server entry: chat.app:app
        logic.py                # Handwritten shared business logic
        service.py              # Handwritten RPC adapters
        rest/services/          # Handwritten REST service implementation
        rest/generated/         # GENERATED Pydantic models + FastAPI router
        v1/                     # GENERATED Protobuf/gRPC/ConnectRPC Python
frontend/
  vue3/
    chat/                       # Independent npm/Vite Vue 3 application
      package.json
      openapi-ts.config.ts
      src/App.vue               # Handwritten Vue interface
      src/api.ts                # Handwritten transport selection
      src/gen/                  # GENERATED Protobuf TS + REST client
scripts/
  bootstrap.py                  # npm install, buf dep update, then generate
  generate.py                   # Direct-target generation only
buf.gen.yaml                    # Shared generator-to-target mapping
pyproject.toml                  # Root orchestration, local editable Python app
```

The repeated `chat` in `proto/chat/chat/v1/chat.proto` is intentional:
`proto/chat/` is the project's root and `chat/v1/chat.proto` is its stable
Protobuf import path. This preserves generated `chat.v1` import paths when
projects are extracted into separate repositories.

## Direct generation targets

| Generation step | Final destination |
|---|---|
| Buf Python + gRPC + ConnectRPC | `backend/python/chat/src/chat/v1/` |
| Buf TypeScript + imported Google annotations | `frontend/vue3/chat/src/gen/` |
| Buf REST OpenAPI 3.1 | `proto/chat/gen/openapi/rest/` |
| Buf Connect OpenAPI docs | `proto/chat/gen/openapi/connect/` |
| OpenAPI → Pydantic v2 | `backend/python/chat/src/chat/rest/generated/models.py` |
| OpenAPI → FastAPI routers | `backend/python/chat/src/chat/rest/generated/server/` |
| OpenAPI → Hey API REST TypeScript client | `frontend/vue3/chat/src/gen/rest/` |

**Handwritten vs generated:** only `src/chat/v1`, `src/chat/rest/generated/models.py`,
`src/chat/rest/generated/server`, `frontend/vue3/chat/src/gen`, and
`proto/chat/gen/openapi/*` are cleaned. Other application files and project
manifests are preserved. The Buf ES generator sets `include_imports: true`
so the generated `google/api/annotations_pb.ts` is available to Vite.

## First setup (Windows PowerShell, repository root)

Requirements: Python 3.11+, `uv`, Node.js 22+, npm, and network access for Buf
remote plugins and package setup.

```powershell
uv sync
uv run python scripts/bootstrap.py
uv run pytest tests -q
```

`bootstrap.py` installs npm dependencies inside `frontend/vue3/chat`, runs
`buf dep update` **inside `proto/chat`** (creating its `buf.lock`), lints the
schema, regenerates all targets directly, and verifies them.

### Run applications

In terminal A, **from the Python project's own directory**:

```powershell
cd backend/python/chat
uv sync
uv run chat-server  # or: uv run uvicorn chat.app:app --port 8000
```

The Python project also supports **independent initialization and generation**
(no root Python environment required):

```powershell
cd backend/python/chat
uv sync
uv run python scripts/bootstrap.py
uv run pytest -q
uv run python scripts/generate.py
```

`bootstrap.py` needs a Buf CLI on `PATH` (or the one installed in the Vue
project's `node_modules`), and access to `../../../proto/chat/`. The schema
checkout can later live elsewhere; set `CHAT_PROTO_DIR` to its Buf module root.


In terminal B:

```powershell
cd frontend/vue3/chat
npm run build
npm run dev
```

Open `http://127.0.0.1:5173/` for Vue and `http://127.0.0.1:8000/docs`
for FastAPI Swagger UI. Native gRPC listens on `127.0.0.1:50051`.

After modifying the `.proto` schema, from the repository root:

```powershell
uv run python scripts/generate.py
```

This skips `npm install` and `buf dep update`; it does not copy generated files.
To check all protocols while the backend is running:

```powershell
uv run python -m scripts.smoke
```

## Future independent Git repositories

Each domain now has its own self-contained project:
`proto/chat` (Buf contract), `backend/python/chat` (Python package), and
`frontend/vue3/chat` (npm app). You can split them with `git subtree split`
while preserving history. The root `buf.gen.yaml` and `scripts/` still
coordinate cross-project generation **today**. A future multi-repository
pipeline should publish the versioned Buf contract and generated artifacts
for each consumer rather than referencing other repositories through local
paths. A directory split by itself is not a complete independent build.

## Compatibility notes

`grpc-ecosystem/openapiv3` and the datamodel-code-generator FastAPI server
generator have experimental functionality. Pinned versions and contract tests
are recommended for production usage. `google.api.http` annotations are
required for REST, and `go_package` in the `.proto` is required by the current
OpenAPI plugin (even though no Go app is generated).
