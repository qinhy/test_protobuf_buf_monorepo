"""No copies; generators write into each independent project, safely."""
from pathlib import Path
import re
import tomllib
import pytest

from scripts.generate import (
    ROOT, FRONTEND, FRONTEND_RPC, PROTO, PYTHON_APP, GENERATED_DIRS, GENERATED_FILES,
    check_direct_targets, check_typescript_imports,
)


def test_generator_targets():
    check_direct_targets()
    config=(ROOT/'buf.gen.yaml').read_text()
    outputs=re.findall(r'(?m)^\s*out:\s*(\S+)\s*$',config)
    assert outputs.count('backend/python/chat/src')==4
    assert outputs.count('frontend/python/chat-rpc/src')==4
    assert 'frontend/vue3/chat/src/gen' in outputs
    assert 'proto/chat/gen/openapi/rest' in outputs
    assert 'proto/chat/gen/openapi/connect' in outputs
    block=config.split('- remote: buf.build/bufbuild/es',1)[1].split('- remote:',1)[0]
    assert 'include_imports: true' in block
    assert config.count('include_imports: true')==1
    assert FRONTEND==ROOT/'frontend/vue3/chat'
    assert FRONTEND_RPC==ROOT/'frontend/python/chat-rpc'
    assert PYTHON_APP==ROOT/'backend/python/chat'
    assert PROTO==ROOT/'proto/chat'


def test_backend_is_importable_python_project():
    project=tomllib.loads((PYTHON_APP/'pyproject.toml').read_text())
    assert project['project']['name']=='chat-backend'
    assert (PYTHON_APP/'src/chat/v1/__init__.py').is_file()
    app=(PYTHON_APP/'src/chat/app.py').read_text()
    assert 'from chat.rest.generated.server import create_app' in app
    assert 'from chat.v1.chat_connect import ChatServiceASGIApplication' in app
    assert 'sys.path' not in app


def test_clean_targets_only_generated_locations():
    for path in (*GENERATED_DIRS,*GENERATED_FILES):
        assert path.resolve().is_relative_to(ROOT.resolve())
    assert PYTHON_APP not in GENERATED_DIRS
    assert PYTHON_APP/'src/chat' not in GENERATED_DIRS
    assert FRONTEND/'src' not in GENERATED_DIRS
    assert FRONTEND/'src/gen' in GENERATED_DIRS
    assert FRONTEND_RPC/'src/chat_rpc' not in GENERATED_DIRS
    assert FRONTEND_RPC/'src/chat/v1' in GENERATED_DIRS
    assert PROTO/'chat' not in GENERATED_DIRS
    assert PYTHON_APP/'src/chat/rest/services' not in GENERATED_DIRS


def test_regeneration_cleanup_preserves_handwritten_source(tmp_path,monkeypatch):
    from scripts import generate
    keep={
        'backend/python/chat/pyproject.toml':'manifest',
        'backend/python/chat/src/chat/app.py':'backend app',
        'backend/python/chat/src/chat/rest/services/chat_service.py':'handler',
        'frontend/python/chat-rpc/pyproject.toml':'client manifest',
        'frontend/python/chat-rpc/src/chat_rpc/client.py':'client code',
        'frontend/vue3/chat/src/App.vue':'vue',
        'proto/chat/chat/v1/chat.proto':'schema',
    }
    stale=[
        'backend/python/chat/src/chat/v1/chat_pb2.py',
        'backend/python/chat/src/chat/rest/generated/models.py',
        'backend/python/chat/src/chat/rest/generated/server/old.py',
        'frontend/python/chat-rpc/src/chat/v1/chat_pb2.py',
        'frontend/vue3/chat/src/gen/chat/v1/old_pb.ts',
        'frontend/vue3/chat/src/gen/google/api/old_pb.ts',
        'frontend/vue3/chat/src/gen/rest/old.ts',
        'proto/chat/gen/openapi/rest/old.json',
        'proto/chat/gen/openapi/connect/old.json',
    ]
    for rel,contents in keep.items():
        f=tmp_path/rel
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text(contents)
    for rel in stale:
        f=tmp_path/rel
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text('obsolete')
    monkeypatch.setattr(generate,'ROOT',tmp_path)
    monkeypatch.setattr(generate,'PYTHON_APP',tmp_path/'backend/python/chat')
    monkeypatch.setattr(generate,'FRONTEND_RPC',tmp_path/'frontend/python/chat-rpc')
    monkeypatch.setattr(generate,'GENERATED_DIRS',tuple(tmp_path/p.relative_to(ROOT) for p in GENERATED_DIRS))
    monkeypatch.setattr(generate,'GENERATED_FILES',tuple(tmp_path/p.relative_to(ROOT) for p in GENERATED_FILES))
    generate.clean_generated()
    assert all(not (tmp_path/r).is_file() for r in stale)
    assert all((tmp_path/r).read_text()==contents for r,contents in keep.items())
    assert (tmp_path/'backend/python/chat/src/chat/v1/__init__.py').is_file()
    assert (tmp_path/'frontend/python/chat-rpc/src/chat/v1/__init__.py').is_file()


def test_ts_import_checker_catches_missing_annotation_modules(tmp_path):
    gen=tmp_path/'gen'; source=gen/'chat/v1/chat_pb.ts'
    source.parent.mkdir(parents=True)
    source.write_text('import { file_google_api_annotations } from "../../google/api/annotations_pb";')
    with pytest.raises(RuntimeError,match='annotations_pb'):
        check_typescript_imports(gen)
    ann=gen/'google/api/annotations_pb.ts'
    ann.parent.mkdir(parents=True)
    ann.write_text('import { file_google_api_http } from "./http_pb.js";')
    with pytest.raises(RuntimeError,match='http_pb.js'):
        check_typescript_imports(gen)
    (ann.parent/'http_pb.ts').write_text('export const file_google_api_http = {}')
    check_typescript_imports(gen)
