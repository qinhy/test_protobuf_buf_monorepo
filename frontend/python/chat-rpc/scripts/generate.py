"""Generate Python RPC client stubs from the shared/independently supplied Buf schema.

From frontend/python/chat-rpc:
    uv run python scripts/generate.py

Use CHAT_PROTO_DIR=/path/to/another-repo to build after splitting repositories.
Requires a Buf CLI (on PATH or installed in the monorepo Vue node_modules).
No monorepo root Python environment or backend package is imported.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT.parents[2]
DEFAULT_PROTO = REPO_ROOT / "proto" / "chat"
# The schema repo can be moved independently; point this at its Buf module root.
PROTO = Path(os.environ.get("CHAT_PROTO_DIR", str(DEFAULT_PROTO))).expanduser().resolve()

# Only src/chat/v1 is generator-owned. Handwritten client code in src/chat_rpc is safe.
GENERATED_DIRS = (PROJECT / "src/chat/v1",)


def run(*args: str, cwd: Path = PROJECT) -> None:
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def find_buf() -> str:
    overridden = os.environ.get("BUF_BIN")
    if overridden:
        return overridden
    installed = shutil.which("buf")
    if installed:
        return installed
    filename = "buf.cmd" if os.name == "nt" else "buf"
    local = REPO_ROOT / "frontend/vue3/chat/node_modules/.bin" / filename
    if local.is_file():
        return str(local)
    raise RuntimeError(
        "Buf CLI is missing. Install buf on PATH (or run the monorepo "
        "frontend's npm install), then regenerate. You can also set BUF_BIN."
    )


def check_proto() -> None:
    if not (PROTO / "buf.yaml").is_file() or not (PROTO / "chat/v1/chat.proto").is_file():
        raise RuntimeError(
            f"Buf schema project not found at {PROTO}. "
            "Set CHAT_PROTO_DIR to the schema repo's module root."
        )


def clean_generated() -> None:
    for path in GENERATED_DIRS:
        target = path.resolve()
        if not target.is_relative_to(PROJECT.resolve()) or target == PROJECT.resolve():
            raise RuntimeError(f"Unsafe generated location: {path}")
        if path.is_dir():
            print("[clean]", path.relative_to(PROJECT), flush=True)
            shutil.rmtree(path)
        elif path.exists():
            print("[clean]", path.relative_to(PROJECT), flush=True)
            path.unlink()
    init = PROJECT / "src/chat/v1/__init__.py"
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text(
        '"""Generated chat.v1 API client stubs are placed in this package by Buf."""\n',
        encoding="utf-8",
    )


def generate() -> None:
    check_proto()
    buf = find_buf()
    run(buf, "lint", str(PROTO))
    clean_generated()
    run(buf, "generate", str(PROTO), "--template", str(PROJECT / "buf.gen.yaml"))
    run(sys.executable, "verify.py")
    print("[PASS] Standalone Python RPC client generation completed (no copy step).")


if __name__ == "__main__":
    generate()
