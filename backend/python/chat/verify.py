"""Check generated code before packaging/releasing the Python app."""
from pathlib import Path


def verify(project: Path | None = None) -> None:
    root = project or Path(__file__).resolve().parent
    files = [
        root / "src/chat/v1/chat_pb2.py",
        root / "src/chat/v1/chat_pb2_grpc.py",
        root / "src/chat/v1/chat_connect.py",
        root / "src/chat/rest/generated/models.py",
        root / "src/chat/rest/generated/server/application.py",
        root / "src/chat/rest/generated/server/services.py",
    ]
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise RuntimeError("chat-backend generation incomplete; run scripts/generate.py: " + ", ".join(missing))
    print("[PASS] chat-backend generated files are present")


if __name__ == "__main__":
    verify()
