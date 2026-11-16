"""Install frontend tools, update Buf dependencies, then generate in-place.

From the repo root: `uv sync && uv run python scripts/bootstrap.py`.
For subsequent regeneration: `uv run python scripts/generate.py`.
"""
from __future__ import annotations

import os
import shutil

try:
    from . import generate
except ImportError:
    import generate  # direct `python scripts/bootstrap.py` support

# Re-export these helpers to keep existing tests/scripts compatible.
ROOT = generate.ROOT
FRONTEND = generate.FRONTEND
REST_OPENAPI = generate.REST_OPENAPI
check_rest_openapi = generate.check_rest_openapi
find_buf = generate.find_buf
run = generate.run


def main() -> None:
    if not shutil.which("node"):
        raise SystemExit("Missing Node.js 22+ and npm")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Missing npm")
    run(npm, "install", cwd=FRONTEND)
    buf = find_buf()
    run(buf, "--version")
    # Update dependency lock only at bootstrap, never on normal regeneration.
    run(buf, "dep", "update", cwd=generate.PROTO)
    generate.main()


if __name__ == "__main__":
    main()
