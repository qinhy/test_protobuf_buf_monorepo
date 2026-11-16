"""Independent projects can be installed/built from their own roots."""
import json
from pathlib import Path
import tomllib

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/'backend/python/chat'
FRONTEND=ROOT/'frontend/vue3/chat'
PROTO=ROOT/'proto/chat'


def test_python_application_has_own_manifest():
    app=tomllib.loads((PYTHON/'pyproject.toml').read_text())
    deps=app['project']['dependencies']
    assert app['project']['name']=='chat-backend'
    assert any(s.startswith('fastapi') for s in deps)
    assert any(s.startswith('connectrpc') for s in deps)
    assert any(s.startswith('grpcio') for s in deps)
    assert app['tool']['setuptools']['packages']['find']['where']==['src']
    assert (PYTHON/'src/chat/__init__.py').exists()
    assert (PYTHON/'src/chat/app.py').is_file()
    assert (PYTHON/'src/chat/rest/services/chat_service.py').is_file()
    assert (PYTHON/'README.md').is_file()


def test_root_manages_local_python_app():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert project['tool']['uv']['package'] is False
    assert 'chat-backend==0.1.0' in project['project']['dependencies']
    assert project['tool']['uv']['sources']['chat-backend']=={'path':'backend/python/chat','editable':True}
    assert any(d.startswith('pytest') for d in project['dependency-groups']['dev'])
    assert any(d.startswith('datamodel-code-generator') for d in project['dependency-groups']['dev'])
    assert '.' in project['tool']['pytest']['ini_options']['pythonpath']
    assert (ROOT/'scripts/__init__.py').is_file()


def test_vue_has_own_npm_project():
    pkg=json.loads((FRONTEND/'package.json').read_text())
    assert pkg['name']=='chat-vue3'
    assert '@bufbuild/buf' in pkg['devDependencies']
    assert 'vue' in pkg['dependencies']
    assert (FRONTEND/'src/App.vue').is_file()
    assert (FRONTEND/'src/api.ts').is_file()
    assert '../../../proto/chat/gen/openapi/rest' in (FRONTEND/'openapi-ts.config.ts').read_text()


def test_proto_is_independent_buf_module():
    config=(PROTO/'buf.yaml').read_text()
    assert 'version: v2' in config
    assert 'path: .' in config
    assert 'buf.build/googleapis/googleapis' in config
    assert (PROTO/'chat/v1/chat.proto').is_file()
    assert not (ROOT/'buf.yaml').exists()


def test_bootstrap_prefers_local_buf(tmp_path,monkeypatch):
    from scripts import bootstrap
    monkeypatch.setattr(bootstrap.generate,'FRONTEND',tmp_path)
    local=tmp_path/'node_modules'/'.bin'/('buf.cmd' if bootstrap.os.name=='nt' else 'buf')
    local.parent.mkdir(parents=True)
    local.write_text('stub')
    assert bootstrap.find_buf()==str(local)
