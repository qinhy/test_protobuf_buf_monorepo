"""Transport-neutral domain event model shared across REST, ConnectRPC, and gRPC.

This module intentionally has no dependencies on FastAPI, Pydantic, or Protobuf.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Started:
    """Emitted once at the start of a chat stream."""

    sequence: int
    message_id: str


@dataclass(frozen=True, slots=True)
class Delta:
    """Emitted for each incremental text chunk."""

    sequence: int
    text: str


@dataclass(frozen=True, slots=True)
class Completed:
    """Emitted once when the response finishes successfully."""

    sequence: int
    reply: str


@dataclass(frozen=True, slots=True)
class Failed:
    """Emitted when an application-level failure occurs during streaming."""

    sequence: int
    code: str
    message: str


ChatEvent = Started | Delta | Completed | Failed
