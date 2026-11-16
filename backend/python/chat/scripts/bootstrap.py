"""First-time backend code generation from backend/python/chat.

    uv sync
    uv run python scripts/bootstrap.py

This installs/updates the shared Buf schema's dependencies, then generates
Python Protobuf, gRPC, ConnectRPC, Pydantic models and FastAPI routes locally.
"""
from generate import PROTO, check_proto, find_buf, generate, run


def main() -> None:
    check_proto()
    buf = find_buf()
    run(buf, "--version")
    run(buf, "dep", "update", cwd=PROTO)
    generate()


if __name__ == "__main__":
    main()
