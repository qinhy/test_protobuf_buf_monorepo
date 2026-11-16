# Chat API contract (Buf module)

`chat/v1/chat.proto` is the **only** handwritten schema. `buf.yaml` declares
this folder as an independent Buf module, with a Google API dependency.

The repeated `chat` in `proto/chat/chat/v1/chat.proto` is deliberate:
`proto/chat` is the **project** directory, while `chat/v1/chat.proto` is the
stable Protobuf import path. The latter must not change when the repository
is split into separate Git repositories.

The project has its own `.gitignore`; keep `buf.lock` in version control.

Buf emits REST and Connect OpenAPI documents to `gen/openapi/`; this directory
is generated and should never be manually edited. `buf.lock` (created by
`buf dep update`) should be checked in after the first bootstrap.

From the monorepo root, run `uv run python scripts/bootstrap.py` once and
`uv run python scripts/generate.py` thereafter. The root `buf.gen.yaml`
coordinates outputs to the Python and Vue projects directly.
