"""Check generated client stubs before packaging/running chat-rpc-client."""
from pathlib import Path


def verify(project: Path | None = None) -> None:
    root = project or Path(__file__).resolve().parent
    files = [
        root / "src/chat/v1/chat_pb2.py",
        root / "src/chat/v1/chat_pb2_grpc.py",
        root / "src/chat/v1/chat_connect.py",
    ]
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise RuntimeError(
            "chat-rpc-client generation incomplete; run scripts/generate.py: "
            + ", ".join(missing)
        )
    print("[PASS] chat-rpc-client generated stubs are present")


if __name__ == "__main__":
    verify()
