"""OpenAPI contract tests validating NDJSON stream chunks against x-ndjson-item-schema."""
from __future__ import annotations

import json
from pathlib import Path
import socket

from pydantic import BaseModel, ConfigDict
import pytest

ROOT = Path(__file__).resolve().parents[1]
RPC = ROOT / "src/chat/v1/chat_pb2.py"
ROUTER = ROOT / "src/chat/rest/generated/server/application.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _resolve_ref(spec: dict, schema: dict) -> dict:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    assert ref.startswith("#/"), f"Unsupported JSON pointer: {ref}"
    node = spec
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _validate_against_schema(spec: dict, schema: dict, value: object) -> None:
    resolved = _resolve_ref(spec, schema)
    schema_type = resolved.get("type")
    if schema_type == "object":
        assert isinstance(value, dict), f"Expected object, got {type(value).__name__}"
        for req_key in resolved.get("required", ()):
            assert req_key in value, f"Missing required key {req_key!r} in {value!r}"
        props = resolved.get("properties", {})
        for key, prop_val in value.items():
            if key in props:
                _validate_against_schema(spec, props[key], prop_val)
    elif schema_type == "string":
        assert isinstance(value, str), f"Expected string, got {type(value).__name__}"
    elif schema_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
    elif schema_type == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
    elif schema_type == "boolean":
        assert isinstance(value, bool)

    if "oneOf" in resolved:
        matched = 0
        for branch in resolved["oneOf"]:
            if "not" in branch:
                continue
            try:
                _validate_against_schema(spec, branch, value)
                matched += 1
            except AssertionError:
                continue
        assert matched == 1, f"Value {value!r} matched {matched} oneOf branches in {resolved}"
    if "anyOf" in resolved:
        matched = False
        for branch in resolved["anyOf"]:
            try:
                _validate_against_schema(spec, branch, value)
                matched = True
                break
            except AssertionError:
                continue
        assert matched, f"Value {value!r} matched no anyOf branch in {resolved}"


@pytest.mark.skipif(not RPC.is_file() or not ROUTER.is_file(), reason="Generate backend code first")
def test_openapi_ndjson_contract_and_stream_chunks(monkeypatch):
    from fastapi.testclient import TestClient

    from chat.app import app

    monkeypatch.setenv("GRPC_BIND", f"127.0.0.1:{_free_port()}")
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        stream_op = spec["paths"]["/api/chat/stream"]["post"]
        content = stream_op["responses"]["200"]["content"]
        assert list(content.keys()) == ["application/x-ndjson"]
        ndjson_media = content["application/x-ndjson"]
        assert ndjson_media["schema"]["type"] == "string"
        item_schema = ndjson_media["x-ndjson-item-schema"]

        with client.stream("POST", "/api/chat/stream", json={"text": "contract"}) as res:
            assert res.status_code == 200
            lines = [json.loads(line) for line in res.iter_lines() if line.strip()]

        assert len(lines) >= 3
        for item in lines:
            _validate_against_schema(spec, item_schema, item)

        # Verify generated Pydantic models also keep BaseModel contract.
        from chat.rest.generated import models

        assert issubclass(models.ChatV1SayResponse, BaseModel)
        _ = ConfigDict
