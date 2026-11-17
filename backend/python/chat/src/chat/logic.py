"""The one place where the chat business logic lives."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import uuid4

from chat.events import ChatEvent, Completed, Delta, Failed, Started

REPLY = "Hello! I'm a demo AI assistant. This is a constant reply."


def generate_reply(text: str) -> str:
    """Synchronous helper returning the constant demo reply.

    Replace this (and ``stream_reply``) with an LLM call when ready.
    """
    # The input is deliberately unused by this constant-reply demo.
    return REPLY


async def stream_reply(
    text: str,
    *,
    chunk_size: int = 4,
    delay_seconds: float = 0.05,
) -> AsyncIterator[ChatEvent]:
    """Yield transport-neutral chat events for a single prompt.

    All three transports (REST NDJSON, ConnectRPC, and native gRPC) consume
    this single async generator.
    """
    # The prompt is accepted for future LLM integration; the demo streams REPLY.
    _ = text
    sequence = 1
    yield Started(sequence=sequence, message_id=str(uuid4()))

    for index in range(0, len(REPLY), max(1, chunk_size)):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        chunk = REPLY[index : index + max(1, chunk_size)]
        sequence += 1
        yield Delta(sequence=sequence, text=chunk)

    sequence += 1
    yield Completed(sequence=sequence, reply=REPLY)


async def complete_reply(text: str) -> str:
    """Consume ``stream_reply`` and return the final reply for unary RPCs/REST."""
    final_reply: str | None = None
    async with aclosing(stream_reply(text, delay_seconds=0.0)) as events:
        async for event in events:
            if isinstance(event, Completed):
                final_reply = event.reply
            elif isinstance(event, Failed):
                raise RuntimeError(f"{event.code}: {event.message}")
    if final_reply is None:
        raise RuntimeError("Chat stream ended without a completion event")
    return final_reply
