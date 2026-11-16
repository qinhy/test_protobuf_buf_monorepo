# Migration: per-domain independent projects

Use a **new extraction folder** when upgrading from a previous ZIP; do not
merge blindly and leave old `backend/`, `frontend/vue3/src/`, or `packages/`
output files behind.

| Previously | Now |
|---|---|
| `proto/chat/v1/chat.proto` | `proto/chat/chat/v1/chat.proto` (Buf module root: `proto/chat`) |
| `buf.yaml` (repository root) | `proto/chat/buf.yaml` |
| `packages/chat-proto-python/src/chat/v1/` | `backend/python/chat/src/chat/v1/` |
| `backend/app.py`, `backend/logic.py`, `backend/service.py` | `backend/python/chat/src/chat/` |
| `backend/rest/` | `backend/python/chat/src/chat/rest/` |
| `frontend/vue3/` | `frontend/vue3/chat/` |
| `schema/rest/`, `schema/connect/` | `proto/chat/gen/openapi/rest/`, `proto/chat/gen/openapi/connect/` |
| `uvicorn backend.app:app` | `uvicorn chat.app:app` |

The monorepo root installs the `chat-backend` Python package via an editable
`uv` path dependency. The backend application's public imports are now
`from chat.logic ...`, `from chat.service ...`, and `from chat.v1 ...`.

### First run

```powershell
uv sync
uv run python scripts/bootstrap.py
uv run pytest tests -q
uv run chat-server  # or: uv run uvicorn chat.app:app --port 8000
```

In another terminal:

```powershell
cd frontend/vue3/chat
npm run build
npm run dev
```

Generated files are deliberately not stored in the ZIP; `bootstrap.py` creates
them. Do not edit generated files or copy them into other folders.

### Running from the backend's own uv project root

```powershell
cd backend/python/chat
uv sync
uv run python scripts/bootstrap.py
uv run pytest -q
uv run chat-server  # or: uv run uvicorn chat.app:app --port 8000
```

The backend now has its own `dependency-groups.dev`, `tests/`,
`buf.gen.yaml`, `scripts/bootstrap.py` and `scripts/generate.py`.
It needs the shared Protobuf schema but does **not** import the monorepo's
root Python scripts. When the schema is moved into another repository, set
`CHAT_PROTO_DIR` to its Buf module root.
