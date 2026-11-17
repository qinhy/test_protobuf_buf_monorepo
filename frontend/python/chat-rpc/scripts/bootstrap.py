"""First-time client code generation from frontend/python/chat-rpc.

    uv sync
    uv run python scripts/bootstrap.py

Updates the shared Buf schema's dependencies, then generates Python
Protobuf, gRPC, and ConnectRPC client stubs locally.
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
