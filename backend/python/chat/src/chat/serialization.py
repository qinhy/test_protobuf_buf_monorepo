"""Serializers mapping transport-neutral domain events to Protobuf or NDJSON."""
from __future__ import annotations

import json

from chat.events import ChatEvent, Completed, Delta, Failed, Started
from chat.v1 import chat_pb2 as pb


def to_proto(event: ChatEvent) -> pb.ChatEvent:
    """Convert a domain ``ChatEvent`` to a generated ``chat.v1.ChatEvent`` message."""
    if isinstance(event, Started):
        return pb.ChatEvent(
            sequence=event.sequence,
            start=pb.ChatStart(message_id=event.message_id),
        )
    if isinstance(event, Delta):
        return pb.ChatEvent(
            sequence=event.sequence,
            delta=pb.ChatDelta(text=event.text),
        )
    if isinstance(event, Completed):
        return pb.ChatEvent(
            sequence=event.sequence,
            complete=pb.ChatComplete(reply=event.reply),
        )
    if isinstance(event, Failed):
        return pb.ChatEvent(
            sequence=event.sequence,
            failure=pb.ChatFailure(code=event.code, message=event.message),
        )
    raise TypeError(f"Unsupported event: {type(event)!r}")


def to_ndjson(event: ChatEvent) -> bytes:
    """Serialize a domain ``ChatEvent`` into one UTF-8 NDJSON envelope line."""
    if isinstance(event, Started):
        payload: dict[str, object] = {"start": {"messageId": event.message_id}}
    elif isinstance(event, Delta):
        payload = {"delta": {"text": event.text}}
    elif isinstance(event, Completed):
        payload = {"complete": {"reply": event.reply}}
    elif isinstance(event, Failed):
        payload = {"failure": {"code": event.code, "message": event.message}}
    else:
        raise TypeError(f"Unsupported event: {type(event)!r}")

    envelope = {
        "result": {
            "sequence": event.sequence,
            **payload,
        }
    }
    return (json.dumps(envelope, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def ndjson_error(code: int, message: str) -> bytes:
    """Serialize an unexpected post-headers stream failure as a top-level error line."""
    envelope = {"error": {"code": code, "message": message}}
    return (json.dumps(envelope, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
