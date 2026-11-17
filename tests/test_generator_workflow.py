"""Guard the independent module input and cross-project generation order."""
from pathlib import Path
import inspect
from scripts import generate,bootstrap


def test_buf_is_invoked_with_independent_proto_module():
    script=inspect.getsource(generate.main)
    assert 'run(buf, "lint", "proto/chat")' in script
    assert 'run(buf, "generate", "proto/chat", "--template", "buf.gen.yaml")' in script
    boot=inspect.getsource(bootstrap.main)
    assert 'run(buf, "dep", "update", cwd=generate.PROTO)' in boot


def test_python_release_gate_runs_after_models_and_router_generation():
    code=inspect.getsource(generate.main)
    assert code.index('"--generate-server", "fastapi"') < code.index('"backend/python/chat/verify.py"')
    assert code.index('"backend/python/chat/verify.py"') < code.index('"generate:rest"')


def test_independent_projects_have_own_ignore_rules():
    for project in (generate.PROTO, generate.PYTHON_APP, generate.FRONTEND, generate.FRONTEND_RPC):
        assert (project/'.gitignore').is_file()
    assert 'buf.lock' not in [line.strip() for line in (generate.PROTO/'.gitignore').read_text().splitlines() if not line.strip().startswith('#')]
