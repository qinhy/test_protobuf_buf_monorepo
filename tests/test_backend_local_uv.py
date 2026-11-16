"""The backend must run from its own cwd, independently of root uv config."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend/python/chat"


def test_independent_uv_project():
    cfg = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert cfg["project"]["name"] == "chat-backend"
    assert cfg["project"]["scripts"]["chat-server"] == "chat.cli:main"
    assert any(d.startswith("pytest") for d in cfg["dependency-groups"]["dev"])
    assert any(d.startswith("datamodel-code-generator") for d in cfg["dependency-groups"]["dev"])
    assert cfg["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert (BACKEND / "tests/test_logic.py").exists()
    assert (BACKEND / "scripts/generate.py").exists()
    assert (BACKEND / "scripts/bootstrap.py").exists()


def test_backend_generator_is_project_local():
    config = (BACKEND / "buf.gen.yaml").read_text()
    assert config.count("out: src") == 4
    assert "out: .generated/openapi/rest" in config
    script = (BACKEND / "scripts/generate.py").read_text()
    assert "CHAT_PROTO_DIR" in script
    assert "--server-package" in script and "chat.rest.generated.server" in script
    assert "from scripts.generate" not in script
    assert 'PROJECT / "src/chat/v1"' in script
    assert 'run(buf, "generate"' in script
