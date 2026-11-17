"""Verify independent uv project and local, direct-target generator metadata."""
from pathlib import Path
import tomllib

BACKEND = Path(__file__).resolve().parents[1]


def test_local_dependencies_and_tests():
    cfg = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert cfg["project"]["name"] == "chat-backend"
    assert cfg["project"]["scripts"]["chat-server"] == "chat.cli:main"
    assert "dev" in cfg["dependency-groups"]
    assert any(dep.startswith("pytest") for dep in cfg["dependency-groups"]["dev"])
    assert any(dep.startswith("datamodel-code-generator") for dep in cfg["dependency-groups"]["dev"])
    assert cfg["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_local_generation_has_no_parent_script_dependency():
    gen = (BACKEND / "scripts/generate.py").read_text()
    assert "from scripts.generate" not in gen
    assert "from chat." not in gen  # can generate before RPC files exist
    assert "--server-layout" in gen and '"single"' in gen
    assert "--server-handler-mode" in gen and '"async"' in gen
    assert "--server-include-request" in gen
    assert "--server-operation-names" in gen
    config = (BACKEND / "buf.gen.yaml").read_text()
    assert config.count("out: src") == 4
    assert "out: .generated/openapi/rest" in config
    assert (BACKEND / "scripts/bootstrap.py").is_file()


def test_server_import_is_local():
    app = (BACKEND / "src/chat/app.py").read_text()
    assert "from chat.v1.chat_connect" in app
    assert "from chat.rest.generated.server import" in app
    assert "build_router" in app
    assert "from backend" not in app
