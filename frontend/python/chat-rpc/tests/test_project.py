"""Verify independent frontend Python RPC client project and generator safety."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy
import tomllib

import pytest

CLIENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = CLIENT_ROOT / "scripts/generate.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("chat_rpc_local_generate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_independent_client_manifest():
    cfg = tomllib.loads((CLIENT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert cfg["project"]["name"] == "chat-rpc-client"
    assert cfg["project"]["scripts"]["chat-rpc-demo"] == "chat_rpc.cli:main"
    deps = cfg["project"]["dependencies"]
    assert any(d.startswith("grpcio") for d in deps)
    assert any(d.startswith("connectrpc") for d in deps)
    assert not any(d.startswith(("fastapi", "uvicorn")) for d in deps)
    assert cfg["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_client_has_no_backend_imports():
    for file in (CLIENT_ROOT / "src/chat_rpc").glob("*.py"):
        source = file.read_text(encoding="utf-8")
        assert "chat.logic" not in source
        assert "chat.app" not in source
        assert "chat.service" not in source
        assert "fastapi" not in source


def test_client_generator_only_outputs_stubs():
    config = (CLIENT_ROOT / "buf.gen.yaml").read_text(encoding="utf-8")
    assert config.count("out: src") == 4
    assert "openapiv3" not in config
    gen = SCRIPT.read_text(encoding="utf-8")
    assert "CHAT_PROTO_DIR" in gen
    assert "from scripts.generate" not in gen


def test_cleanup_preserves_handwritten_client(tmp_path, monkeypatch):
    generator = _load_generator()
    handwritten = tmp_path / "src/chat_rpc/client.py"
    stale_stub = tmp_path / "src/chat/v1/old_pb2.py"
    for file in (handwritten, stale_stub):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("sample", encoding="utf-8")

    monkeypatch.setattr(generator, "PROJECT", tmp_path)
    monkeypatch.setattr(generator, "GENERATED_DIRS", (tmp_path / "src/chat/v1",))
    generator.clean_generated()

    assert handwritten.read_text(encoding="utf-8") == "sample"
    assert not stale_stub.exists()
    assert (tmp_path / "src/chat/v1/__init__.py").is_file()


def test_verify_requires_generated_stubs(tmp_path):
    verify = runpy.run_path(str(CLIENT_ROOT / "verify.py"))["verify"]
    with pytest.raises(RuntimeError, match="generation incomplete"):
        verify(tmp_path)
    for rel in (
        "src/chat/v1/chat_pb2.py",
        "src/chat/v1/chat_pb2_grpc.py",
        "src/chat/v1/chat_connect.py",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# generated", encoding="utf-8")
    verify(tmp_path)
