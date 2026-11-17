"""Post-generation check: no server startup or native gRPC port needed.

This verifies the generated FastAPI router, request/response Pydantic models,
service interface, unary + NDJSON streaming responses, and source-derived OpenAPI agree.
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from chat.logic import REPLY
from chat.rest.generated.server import (
    build_router,
    serve_source_openapi,
    validation_error_handler,
)
from chat.rest.services.chat import ChatRestService


def main() -> None:
    api = FastAPI()
    api.add_exception_handler(RequestValidationError, validation_error_handler)
    api.include_router(build_router(service=ChatRestService()))
    serve_source_openapi(api)

    with TestClient(api) as client:
        response = client.post("/api/chat", json={"text": "Hello generated FastAPI"})
        assert response.status_code == 200, response.text
        assert response.json() == {"reply": REPLY}, response.text

        bad = client.post("/api/chat", json={"text": "   "})
        assert bad.status_code == 422, bad.text

        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"text": "Hello NDJSON"},
            headers={"Accept": "application/x-ndjson"},
        ) as stream_res:
            assert stream_res.status_code == 200, stream_res.text
            assert stream_res.headers["content-type"].startswith("application/x-ndjson")
            lines = [json.loads(line) for line in stream_res.iter_lines() if line.strip()]

        assert lines[0]["result"]["sequence"] == 1
        assert "start" in lines[0]["result"]
        deltas = "".join(
            item["result"]["delta"]["text"]
            for item in lines
            if "delta" in item["result"]
        )
        assert deltas == REPLY
        assert lines[-1]["result"]["complete"]["reply"] == REPLY

        bad_stream = client.post("/api/chat/stream", json={"text": "   "})
        assert bad_stream.status_code == 422, bad_stream.text

        spec = client.get("/openapi.json").json()
        assert "/api/chat" in spec["paths"]
        stream_op = spec["paths"]["/api/chat/stream"]["post"]
        ndjson_media = stream_op["responses"]["200"]["content"]["application/x-ndjson"]
        assert "x-ndjson-item-schema" in ndjson_media

    print("[PASS] generated OpenAPI -> Pydantic -> FastAPI REST service (unary + NDJSON)")


if __name__ == "__main__":
    main()
