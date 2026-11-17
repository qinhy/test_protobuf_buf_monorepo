"""Handwritten REST service implementing the generated ``Service`` Protocol.

Request models, routes, and OpenAPI schema come from ``chat.rest.generated``.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from chat.logic import complete_reply, stream_reply
from chat.rest.generated import models
from chat.rest.generated.server.services import Service
from chat.serialization import ndjson_error, to_ndjson

logger = logging.getLogger(__name__)


def _validate_text(text: str | None) -> str:
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="text must be nonempty")
    return text


class ChatRestService(Service):
    """REST service implementing unary ``say`` and NDJSON streaming ``stream_say``."""

    async def say(
        self,
        *,
        request: Request,
        body: Any,
    ) -> models.ChatV1SayResponse:
        _ = request
        text = _validate_text(body.text)
        return models.ChatV1SayResponse(reply=await complete_reply(text))

    async def stream_say(
        self,
        *,
        request: Request,
        body: Any,
    ) -> StreamingResponse:
        text = _validate_text(body.text)

        async def generate() -> AsyncIterator[bytes]:
            try:
                async with aclosing(stream_reply(text)) as events:
                    async for event in events:
                        if await request.is_disconnected():
                            return
                        yield to_ndjson(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Chat stream failed")
                yield ndjson_error(13, "internal error")

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )
