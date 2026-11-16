"""Per-domain project boundaries and Python packaging/release gate."""
from pathlib import Path
import runpy
import pytest

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/'backend/python/chat'


def test_application_and_generated_bindings_are_in_one_python_project():
    assert (PYTHON/'pyproject.toml').exists()
    assert (PYTHON/'src/chat/app.py').exists()
    assert (PYTHON/'src/chat/logic.py').exists()
    assert (PYTHON/'src/chat/v1/__init__.py').exists()
    assert (PYTHON/'src/chat/rest/generated/__init__.py').exists()
    assert (PYTHON/'src/chat/rest/services/chat_service.py').exists()
    assert not (ROOT/'packages/chat-proto-python').exists()


def test_import_paths_are_stable():
    app=(PYTHON/'src/chat/app.py').read_text()
    service=(PYTHON/'src/chat/service.py').read_text()
    assert 'from chat.v1.' in app
    assert 'from chat.v1.' in service
    assert 'from chat.logic import generate_reply' in service
    assert 'from backend.' not in app+service


def test_release_gate_requires_all_generated_artifacts(tmp_path):
    verify=runpy.run_path(str(PYTHON/'verify.py'))['verify']
    with pytest.raises(RuntimeError, match='generation incomplete'):
        verify(tmp_path)
    filenames=[
        'src/chat/v1/chat_pb2.py',
        'src/chat/v1/chat_pb2_grpc.py',
        'src/chat/v1/chat_connect.py',
        'src/chat/rest/generated/models.py',
        'src/chat/rest/generated/server/application.py',
    ]
    for name in filenames:
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('# generated')
    verify(tmp_path)
