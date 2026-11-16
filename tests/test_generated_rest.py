"""Protobuf is the only schema, OpenAPI is generated in its own project."""
import json
from pathlib import Path
import pytest
from scripts.generate import ROOT, PROTO, PYTHON_APP, FRONTEND, REST_OPENAPI, check_rest_openapi


def test_proto_contains_rest_mapping():
    proto=(PROTO/'chat/v1/chat.proto').read_text()
    assert 'package chat.v1' in proto
    assert 'import "google/api/annotations.proto";' in proto
    assert 'post: "/api/chat"' in proto
    assert 'body: "*"' in proto
    assert 'option go_package = ' in proto
    assert 'rpc Say(SayRequest) returns (SayResponse)' in proto


def test_generated_rest_is_not_handwritten():
    app=(PYTHON_APP/'src/chat/app.py').read_text()
    assert '@app.post("/api/chat"' not in app
    assert 'create_app(chat_service=ChatService()' in app
    assert not (PYTHON_APP/'src/chat/proto_pydantic.py').exists()
    cfg=(ROOT/'buf.gen.yaml').read_text()
    assert 'grpc-ecosystem/openapiv3' in cfg
    assert 'out: backend/python/chat/src' in cfg
    assert 'out: frontend/vue3/chat/src/gen' in cfg
    assert 'out: proto/chat/gen/openapi/rest' in cfg


def test_generated_openapi_contract_validation(tmp_path):
    spec={'openapi':'3.1.0','paths':{'/api/chat':{'post':{
        'operationId':'ChatService_Say','tags':['ChatService'],
        'requestBody':{'content':{'application/json':{'schema':{'type':'object'}}}},
        'responses':{'200':{'description':'ok'}},
    }}}}
    filename=tmp_path/'chat.openapi.json'
    filename.write_text(json.dumps(spec))
    check_rest_openapi(filename)
    del spec['paths']['/api/chat']['post']['requestBody']
    filename.write_text(json.dumps(spec))
    with pytest.raises(RuntimeError):
        check_rest_openapi(filename)


@pytest.mark.skipif(not REST_OPENAPI.exists(),reason='Generate OpenAPI first')
def test_actual_rest_openapi():
    check_rest_openapi()
