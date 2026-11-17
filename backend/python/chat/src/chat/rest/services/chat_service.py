"""Compatibility shim; REST implementation lives in ``chat.rest.services.chat``."""
from __future__ import annotations

from chat.rest.services.chat import ChatRestService

ChatService = ChatRestService

__all__ = ["ChatRestService", "ChatService"]
