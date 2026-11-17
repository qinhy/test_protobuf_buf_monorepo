"""Unit tests for proto/chat/scripts/normalize_openapi.py without requiring Buf CLI."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from google.api import annotations_pb2
from google.protobuf import descriptor_pb2
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "proto/chat/scripts/normalize_openapi.py"


def _load_normalizer():
    spec = importlib.util.spec_from_file_location("proto_chat_normalize_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_test_descriptor_bytes() -> bytes:
    fds = descriptor_pb2.FileDescriptorSet()
    f = fds.file.add()
    f.name = "chat/v1/chat.proto"
    f.package = "chat.v1"
    svc = f.service.add()
    svc.name = "ChatService"

    unary = svc.method.add()
    unary.name = "Say"
    unary.server_streaming = False
    unary.options.Extensions[annotations_pb2.http].post = "/api/chat"

    stream = svc.method.add()
    stream.name = "StreamSay"
    stream.server_streaming = True
    stream.options.Extensions[annotations_pb2.http].post = "/api/chat/stream"

    return fds.SerializeToString()


def test_normalize_openapi_rewrites_streaming_response_and_preserves_chunk_schema(tmp_path):
    normalizer = _load_normalizer()
    descriptor_path = tmp_path / "descriptor.binpb"
    descriptor_path.write_bytes(_build_test_descriptor_bytes())

    openapi_path = tmp_path / "chat.openapi.json"
    source_spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/chat": {
                "post": {
                    "operationId": "ChatService_Say",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/chat.v1.SayResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/chat/stream": {
                "post": {
                    "operationId": "ChatService_StreamSay",
                    "responses": {
                        "200": {
                            "description": "A successful response.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/StreamResultOfChatEvent"}
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    openapi_path.write_text(json.dumps(source_spec), encoding="utf-8")

    result = normalizer.normalize_openapi(openapi_path, descriptor_path)

    # Unary route remains application/json.
    assert "application/json" in result["paths"]["/api/chat"]["post"]["responses"]["200"]["content"]

    # Streaming route is rewritten to application/x-ndjson with preserved chunk schema.
    stream_resp = result["paths"]["/api/chat/stream"]["post"]["responses"]["200"]
    assert stream_resp["description"] == "Incremental chat events"
    assert list(stream_resp["content"].keys()) == ["application/x-ndjson"]
    ndjson = stream_resp["content"]["application/x-ndjson"]
    assert ndjson["schema"]["type"] == "string"
    assert ndjson["x-ndjson-item-schema"] == {"$ref": "#/components/schemas/StreamResultOfChatEvent"}


def test_normalize_openapi_fails_when_generator_structure_changes(tmp_path):
    normalizer = _load_normalizer()
    descriptor_path = tmp_path / "descriptor.binpb"
    descriptor_path.write_bytes(_build_test_descriptor_bytes())

    openapi_path = tmp_path / "chat.openapi.json"
    openapi_path.write_text(
        json.dumps({"openapi": "3.1.0", "paths": {"/api/chat/stream": {"post": {"responses": {"200": {"content": {}}}}}}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="application/json"):
        normalizer.normalize_openapi(openapi_path, descriptor_path)
