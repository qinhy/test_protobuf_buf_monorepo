"""Regenerate every target directly in-place. No copy phase.

First time: `uv run python scripts/bootstrap.py`.
Later:      `uv run python scripts/generate.py`.

Only the explicitly named generated targets below may be deleted. The Python application
package manifest, handwritten services, and Vue components are never touched.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "vue3" / "chat"
PROTO = ROOT / "proto" / "chat"
PYTHON_APP = ROOT / "backend" / "python" / "chat"
REST_OPENAPI = PROTO / "gen" / "openapi" / "rest" / "chat" / "v1" / "chat.openapi.json"


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def find_buf() -> str:
    filename = "buf.cmd" if os.name == "nt" else "buf"
    local = FRONTEND / "node_modules" / ".bin" / filename
    if local.is_file():
        return str(local)
    global_buf = shutil.which("buf")
    if global_buf:
        return global_buf
    raise SystemExit("Buf CLI not found. Run `uv run python scripts/bootstrap.py` first.")


def check_rest_openapi(path: Path = REST_OPENAPI) -> None:
    if not path.is_file():
        raise RuntimeError(f"Expected generated OpenAPI missing: {path}")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not spec.get("openapi", "").startswith("3."):
        raise RuntimeError("REST code generation requires OpenAPI 3.x")
    post = spec.get("paths", {}).get("/api/chat", {}).get("post")
    if not post or not post.get("requestBody") or not post.get("responses", {}).get("200"):
        raise RuntimeError("Protobuf HTTP mapping must generate POST /api/chat with JSON body and 200 response")
    if post.get("operationId") != "ChatService_Say":
        raise RuntimeError(f"Unexpected REST operation id: {post.get('operationId')}")
    if not post.get("tags") or post["tags"][0] != "ChatService":
        raise RuntimeError(f"Unexpected REST service tag: {post.get('tags')}")


# Safe-to-delete locations with generated files ONLY. `chat/v1/__init__.py`
# is recreated to keep the local generated Python distribution importable.
GENERATED_DIRS = (
    PYTHON_APP / "src/chat/v1",
    # Both Buf ES and Hey API write here. Treat ALL of src/gen as generated.
    # Removes stale google/api imports when proto dependencies change.
    FRONTEND / "src/gen",
    PROTO / "gen/openapi/rest",
    PROTO / "gen/openapi/connect",
    PYTHON_APP / "src/chat/rest/generated/server",
)
GENERATED_FILES = (PYTHON_APP / "src/chat/rest/generated/models.py",)


def clean_generated() -> None:
    for path in (*GENERATED_DIRS, *GENERATED_FILES):
        # Prevent accidental cleanup outside this repository if someone changes paths.
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
            raise RuntimeError(f"Unsafe generated destination: {path}")
        if path.is_dir():
            print(f"[clean] {path.relative_to(ROOT)}", flush=True)
            shutil.rmtree(path)
        elif path.exists():
            print(f"[clean] {path.relative_to(ROOT)}", flush=True)
            path.unlink()
    python_init = PYTHON_APP / "src/chat/v1/__init__.py"
    python_init.parent.mkdir(parents=True, exist_ok=True)
    python_init.write_text('"""Generated chat.v1 API modules are placed in this package by Buf."""\n', encoding="utf-8")


def check_direct_targets() -> None:
    import tomllib
    cfg = (ROOT / "buf.gen.yaml").read_text(encoding="utf-8")
    outs = set(re.findall(r"(?m)^\s*out:\s*(\S+)\s*$", cfg))
    required = {"backend/python/chat/src", "frontend/vue3/chat/src/gen", "proto/chat/gen/openapi/rest", "proto/chat/gen/openapi/connect"}
    if not required.issubset(outs):
        raise RuntimeError(f"Unexpected Buf output mapping, missing: {required - outs}")
    # Without this option the generated chat_pb.ts imports google/api/annotations_pb
    # but Buf does not emit its TypeScript module, causing Vite import errors.
    es_plugin = cfg.split("- remote: buf.build/bufbuild/es", 1)
    if len(es_plugin) != 2 or "include_imports: true" not in es_plugin[1].split("- remote:", 1)[0]:
        raise RuntimeError("Buf ES plugin must set include_imports: true for google/api annotations")
    # The standalone Python app needs to be an editable local dependency.
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    source = proj.get("tool", {}).get("uv", {}).get("sources", {}).get("chat-backend", {})
    if source != {"path": "backend/python/chat", "editable": True}:
        raise RuntimeError("Expected chat-backend as a local editable dependency")


def check_typescript_imports(gen_dir: Path | None = None) -> None:
    """Fail immediately when a generated TS module imports an absent local module.

    This catches missing Google API annotation dependencies during code generation,
    rather than first surfacing as an obscure Vite import-analysis error.
    """
    gen_dir = gen_dir or FRONTEND / "src/gen"
    chat_file = gen_dir / "chat/v1/chat_pb.ts"
    if not chat_file.is_file():
        raise RuntimeError(f"Expected generated TypeScript missing: {chat_file}")
    # ES uses extensionless relative imports; also support explicit JS extensions.
    # Nonrelative package imports (e.g. @bufbuild/protobuf) are npm's responsibility.
    relative_import = re.compile(r"\bfrom\s*['\"](\.[^'\"]+)['\"]|\bimport\s*['\"](\.[^'\"]+)['\"]")
    unresolved = []
    for source in gen_dir.rglob("*.ts"):
        for match in relative_import.finditer(source.read_text(encoding="utf-8")):
            specifier = match.group(1) or match.group(2)
            target = (source.parent / specifier).resolve()
            # Protoc ES may emit relative '.js' specifiers for TypeScript output.
            candidates = [target, Path(str(target) + ".ts"), Path(str(target) + ".tsx"), target / "index.ts"]
            if target.suffix == ".js":
                candidates.append(target.with_suffix(".ts"))
            if not any(candidate.is_file() for candidate in candidates):
                unresolved.append(f"{source.relative_to(gen_dir)}: {specifier}")
    if unresolved:
        raise RuntimeError(
            "Unresolved generated TypeScript imports; check Buf ES include_imports.\n"
            + "\n".join(unresolved)
        )


def main() -> None:
    buf = find_buf()
    check_direct_targets()
    run(buf, "lint", "proto/chat")
    clean_generated()
    run(buf, "generate", "proto/chat", "--template", "buf.gen.yaml")
    check_rest_openapi()
    rpc_file = PYTHON_APP / "src/chat/v1/chat_pb2.py"
    ts_file = FRONTEND / "src/gen/chat/v1/chat_pb.ts"
    if not rpc_file.is_file() or not ts_file.is_file():
        raise RuntimeError("Buf did not generate the expected Python and TypeScript targets")
    check_typescript_imports()
    run(
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(REST_OPENAPI),
        "--input-file-type", "openapi",
        "--openapi-scopes", "schemas", "api",
        "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.11",
        "--no-treat-dot-as-module",
        "--disable-timestamp",
        "--output", "backend/python/chat/src/chat/rest/generated/models.py",
        "--generate-server", "fastapi",
        "--server-output", "backend/python/chat/src/chat/rest/generated/server",
        "--server-package", "chat.rest.generated.server",
        "--server-model-package", "chat.rest.generated.models",
    )
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Missing npm; install Node.js and run bootstrap.py first")
    run(sys.executable, "backend/python/chat/verify.py")
    run(npm, "run", "generate:rest", cwd=FRONTEND)
    run(sys.executable, "-m", "scripts.check_generated_rest")
    print("\nAll targets generated in place. No files copied.")


if __name__ == "__main__":
    main()
