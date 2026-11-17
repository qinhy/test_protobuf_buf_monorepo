"""Safety checks for the backend-local generation script (no remote Buf needed)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("chat_backend_local_generate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_cleanup_only_removes_generated_code(tmp_path, monkeypatch):
    generator = load_generator()
    app = tmp_path / "src/chat/app.py"
    handwritten_rest = tmp_path / "src/chat/rest/services/chat.py"
    generated = tmp_path / "src/chat/v1/old_pb2.py"
    model = tmp_path / "src/chat/rest/generated/models.py"
    old_route = tmp_path / "src/chat/rest/generated/server/obsolete.py"
    old_scaffold = tmp_path / "src/chat/rest/generated/services/obsolete.py"
    generated_spec = tmp_path / ".generated/openapi/rest/old.json"
    for file in (app, handwritten_rest, generated, model, old_route, old_scaffold, generated_spec):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("sample")

    monkeypatch.setattr(generator, "PROJECT", tmp_path)
    monkeypatch.setattr(generator, "GENERATED_DIRS", (
        tmp_path / "src/chat/v1",
        tmp_path / "src/chat/rest/generated/server",
        tmp_path / "src/chat/rest/generated/services",
        tmp_path / ".generated/openapi/rest",
    ))
    monkeypatch.setattr(generator, "GENERATED_FILES", (model,))
    generator.clean_generated()
    assert app.read_text() == "sample"
    assert handwritten_rest.read_text() == "sample"
    assert not generated.exists() and not model.exists()
    assert not old_route.exists() and not old_scaffold.exists() and not generated_spec.exists()
    assert (tmp_path / "src/chat/v1/__init__.py").exists()


def test_cleanup_rejects_paths_outside_backend(tmp_path, monkeypatch):
    generator = load_generator()
    project = tmp_path / "backend"
    project.mkdir()
    outside = tmp_path / "keep_me"
    outside.write_text("handwritten")
    monkeypatch.setattr(generator, "PROJECT", project)
    monkeypatch.setattr(generator, "GENERATED_DIRS", (outside,))
    monkeypatch.setattr(generator, "GENERATED_FILES", ())
    with pytest.raises(RuntimeError, match="Unsafe generated"):
        generator.clean_generated()
    assert outside.read_text() == "handwritten"


def test_openapi_check(tmp_path, monkeypatch):
    generator = load_generator()
    path = tmp_path / "chat.openapi.json"
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/chat": {
                "post": {
                    "operationId": "ChatService_Say",
                    "requestBody": {"content": {"application/json": {}}},
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/chat/stream": {
                "post": {
                    "operationId": "ChatService_StreamSay",
                    "requestBody": {"content": {"application/json": {}}},
                    "responses": {
                        "200": {
                            "description": "Incremental chat events",
                            "content": {
                                "application/x-ndjson": {
                                    "schema": {"type": "string"},
                                    "x-ndjson-item-schema": {"$ref": "#/components/schemas/StreamChunk"},
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(generator, "OPENAPI", path)
    generator.check_openapi()

    spec["paths"]["/api/chat/stream"]["post"]["responses"]["200"]["content"] = {
        "application/json": {"schema": {"$ref": "#/components/schemas/StreamChunk"}}
    }
    path.write_text(json.dumps(spec))
    with pytest.raises(RuntimeError, match="/api/chat/stream"):
        generator.check_openapi()
