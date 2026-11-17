"""Normalize server-streaming HTTP bindings in generated OpenAPI 3.1 specs to NDJSON.

Reads a Buf FileDescriptorSet (`buf build --as-file-descriptor-set -o ...`),
locates RPCs with `server_streaming = true` and a `(google.api.http)` annotation,
and rewrites their OpenAPI 200 response media type to `application/x-ndjson`
while preserving the generated chunk schema under `x-ndjson-item-schema`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

# Protobuf wire types
_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_SGROUP = 3
_WIRE_EGROUP = 4
_WIRE_32BIT = 5

# google.api.http extension number on google.protobuf.MethodOptions
_HTTP_OPTION_TAG = 72295728


@dataclass(frozen=True, slots=True)
class StreamingHttpBinding:
    """HTTP binding extracted for a server-streaming RPC."""

    package: str
    service: str
    rpc: str
    http_method: str
    http_path: str


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, pos
        shift += 7
    raise ValueError("Truncated varint in protobuf descriptor")


def _iter_fields(buf: bytes):
    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        if wire_type == _WIRE_VARINT:
            val, pos = _read_varint(buf, pos)
            yield field_num, wire_type, val
        elif wire_type == _WIRE_64BIT:
            if pos + 8 > end:
                raise ValueError("Truncated 64-bit field in protobuf descriptor")
            yield field_num, wire_type, buf[pos : pos + 8]
            pos += 8
        elif wire_type == _WIRE_LEN:
            length, pos = _read_varint(buf, pos)
            if pos + length > end:
                raise ValueError("Truncated length-delimited field in protobuf descriptor")
            yield field_num, wire_type, buf[pos : pos + length]
            pos += length
        elif wire_type == _WIRE_32BIT:
            if pos + 4 > end:
                raise ValueError("Truncated 32-bit field in protobuf descriptor")
            yield field_num, wire_type, buf[pos : pos + 4]
            pos += 4
        elif wire_type == _WIRE_SGROUP:
            # Skip deprecated group if encountered.
            depth = 1
            while depth > 0:
                sub_tag, pos = _read_varint(buf, pos)
                sub_wire = sub_tag & 0x07
                if sub_wire == _WIRE_SGROUP:
                    depth += 1
                elif sub_wire == _WIRE_EGROUP:
                    depth -= 1
                elif sub_wire == _WIRE_VARINT:
                    _, pos = _read_varint(buf, pos)
                elif sub_wire == _WIRE_64BIT:
                    pos += 8
                elif sub_wire == _WIRE_LEN:
                    length, pos = _read_varint(buf, pos)
                    pos += length
                elif sub_wire == _WIRE_32BIT:
                    pos += 4
                else:
                    raise ValueError(f"Unsupported wire type {sub_wire} inside group")
            yield field_num, wire_type, b""
        else:
            raise ValueError(f"Unsupported wire type {wire_type} in protobuf descriptor")


def _parse_http_rule(buf: bytes) -> tuple[str, str] | None:
    method_by_field = {
        2: "GET",
        3: "PUT",
        4: "POST",
        5: "DELETE",
        6: "PATCH",
    }
    for field_num, wire_type, value in _iter_fields(buf):
        if wire_type == _WIRE_LEN and field_num in method_by_field:
            return method_by_field[field_num], value.decode("utf-8")
    return None


def _parse_method_options(buf: bytes) -> tuple[str, str] | None:
    for field_num, wire_type, value in _iter_fields(buf):
        if field_num == _HTTP_OPTION_TAG and wire_type == _WIRE_LEN:
            parsed = _parse_http_rule(value)
            if parsed is not None:
                return parsed
    return None


def _parse_method(buf: bytes) -> tuple[str, bool, tuple[str, str] | None]:
    name = ""
    server_streaming = False
    http_binding: tuple[str, str] | None = None
    for field_num, wire_type, value in _iter_fields(buf):
        if field_num == 1 and wire_type == _WIRE_LEN:
            name = value.decode("utf-8")
        elif field_num == 4 and wire_type == _WIRE_LEN:
            http_binding = _parse_method_options(value)
        elif field_num == 6 and wire_type == _WIRE_VARINT:
            server_streaming = bool(value)
    return name, server_streaming, http_binding


def _parse_service(buf: bytes) -> tuple[str, list[tuple[str, bool, tuple[str, str] | None]]]:
    name = ""
    methods: list[tuple[str, bool, tuple[str, str] | None]] = []
    for field_num, wire_type, value in _iter_fields(buf):
        if field_num == 1 and wire_type == _WIRE_LEN:
            name = value.decode("utf-8")
        elif field_num == 2 and wire_type == _WIRE_LEN:
            methods.append(_parse_method(value))
    return name, methods


def find_streaming_http_bindings(descriptor_bytes: bytes) -> list[StreamingHttpBinding]:
    """Return HTTP bindings for all server-streaming RPCs in a FileDescriptorSet."""
    bindings: list[StreamingHttpBinding] = []
    for file_field, file_wire, file_bytes in _iter_fields(descriptor_bytes):
        if file_field != 1 or file_wire != _WIRE_LEN:
            continue
        package = ""
        services: list[bytes] = []
        for field_num, wire_type, value in _iter_fields(file_bytes):
            if field_num == 2 and wire_type == _WIRE_LEN:
                package = value.decode("utf-8")
            elif field_num == 6 and wire_type == _WIRE_LEN:
                services.append(value)
        for svc_bytes in services:
            svc_name, methods = _parse_service(svc_bytes)
            for rpc_name, server_streaming, http_binding in methods:
                if server_streaming and http_binding is not None:
                    http_method, http_path = http_binding
                    bindings.append(
                        StreamingHttpBinding(
                            package=package,
                            service=svc_name,
                            rpc=rpc_name,
                            http_method=http_method,
                            http_path=http_path,
                        )
                    )
    return bindings


def _dereference_schema(
    node: Any,
    schemas: dict[str, Any],
    seen: frozenset[str] = frozenset(),
) -> Any:
    """Inline local `#/components/schemas/...` refs so vendor extensions stay self-contained."""
    if isinstance(node, list):
        return [_dereference_schema(item, schemas, seen) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.removeprefix("#/components/schemas/")
        if name in schemas and name not in seen:
            merged = dict(schemas[name])
            for key, val in node.items():
                if key != "$ref":
                    merged[key] = val
            return _dereference_schema(merged, schemas, seen | {name})
    return {
        key: _dereference_schema(val, schemas, seen)
        for key, val in node.items()
    }


def normalize_openapi_spec(spec: dict[str, Any], bindings: list[StreamingHttpBinding]) -> dict[str, Any]:
    """Rewrite streaming 200 JSON responses in `spec` to `application/x-ndjson`."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI document missing 'paths' object")
    schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        schemas = {}

    for binding in bindings:
        path_item = paths.get(binding.http_path)
        if not isinstance(path_item, dict):
            raise RuntimeError(f"Streaming path missing from OpenAPI: {binding.http_path}")
        op = path_item.get(binding.http_method.lower())
        if not isinstance(op, dict):
            raise RuntimeError(
                f"Streaming operation {binding.http_method} {binding.http_path} missing from OpenAPI"
            )
        responses = op.get("responses")
        if not isinstance(responses, dict) or not isinstance(responses.get("200"), dict):
            raise RuntimeError(
                f"Streaming operation {binding.http_method} {binding.http_path} missing 200 response"
            )
        resp_200 = responses["200"]
        content = resp_200.get("content")
        if not isinstance(content, dict):
            raise RuntimeError(
                f"Streaming operation {binding.http_method} {binding.http_path} 200 response missing content"
            )

        if "application/x-ndjson" in content and "x-ndjson-item-schema" in content["application/x-ndjson"]:
            continue

        json_media = content.get("application/json")
        if not isinstance(json_media, dict) or "schema" not in json_media:
            raise RuntimeError(
                f"Expected application/json schema on streaming operation {binding.http_method} {binding.http_path}"
            )

        chunk_schema = _dereference_schema(json_media["schema"], schemas)
        resp_200["description"] = "Incremental chat events"
        resp_200["content"] = {
            "application/x-ndjson": {
                "schema": {
                    "type": "string",
                    "description": "UTF-8 NDJSON stream, one JSON object per line.",
                },
                "x-ndjson-item-schema": chunk_schema,
            }
        }
    return spec


def normalize_openapi(openapi_path: Path, descriptor_path: Path) -> dict[str, Any]:
    """Normalize an OpenAPI JSON file in-place using a compiled FileDescriptorSet."""
    descriptor_bytes = descriptor_path.read_bytes()
    bindings = find_streaming_http_bindings(descriptor_bytes)
    if not bindings:
        raise RuntimeError("No server-streaming HTTP bindings found in FileDescriptorSet")
    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    normalized = normalize_openapi_spec(spec, bindings)
    openapi_path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize streaming REST responses in OpenAPI 3.1 to NDJSON.")
    parser.add_argument("--openapi", type=Path, required=True, help="Path to generated chat.openapi.json")
    parser.add_argument("--descriptor", type=Path, required=True, help="Path to Buf FileDescriptorSet binary")
    args = parser.parse_args(argv)
    normalize_openapi(args.openapi, args.descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
