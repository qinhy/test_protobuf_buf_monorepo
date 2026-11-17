"""Native gRPC and ConnectRPC client calls built from generated chat.v1 stubs."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
import time
from typing import Literal

from connectrpc.compat import (
    google_protobuf_binary_codec,
    google_protobuf_json_codec,
)
from connectrpc.protocol import ProtocolType
import grpc

from chat.v1.chat_connect import ChatServiceClient
from chat.v1.chat_pb2 import ChatEvent, SayRequest
from chat.v1.chat_pb2_grpc import ChatServiceStub

ConnectTransport = Literal["connect-binary", "connect-json", "grpc-web"]
Transport = Literal["grpc", "connect-binary", "connect-json", "grpc-web"]
TransportSelection = Literal["grpc", "connect-binary", "connect-json", "grpc-web", "all"]

ALL_TRANSPORTS: tuple[Transport, ...] = (
    "grpc",
    "connect-binary",
    "connect-json",
    "grpc-web",
)

_CONNECT_TRANSPORTS: dict[ConnectTransport, tuple[ProtocolType, bool]] = {
    "connect-binary": (ProtocolType.CONNECT, True),
    "connect-json": (ProtocolType.CONNECT, False),
    "grpc-web": (ProtocolType.GRPC_WEB, True),
}


@dataclass(frozen=True, slots=True)
class RpcResult:
    """Result returned by a single unary RPC invocation."""

    transport: Transport
    target: str
    reply: str
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class StreamResult:
    """Aggregated summary of a server-streaming RPC invocation."""

    transport: Transport
    target: str
    events: tuple[ChatEvent, ...]
    reply: str
    elapsed_ms: float
    first_delta_ms: float | None


async def call_grpc(
    text: str,
    *,
    target: str = "127.0.0.1:50051",
    timeout: float = 5.0,
) -> RpcResult:
    """Call ChatService.Say over native HTTP/2 gRPC."""
    started = time.perf_counter()
    async with grpc.aio.insecure_channel(target) as channel:
        response = await ChatServiceStub(channel).Say(
            SayRequest(text=text),
            timeout=timeout,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return RpcResult(
        transport="grpc",
        target=target,
        reply=response.reply,
        elapsed_ms=elapsed_ms,
    )


async def call_connect(
    text: str,
    *,
    base_url: str = "http://127.0.0.1:8000",
    transport: ConnectTransport = "connect-binary",
    timeout_ms: int = 5000,
) -> RpcResult:
    """Call ChatService.Say using the generated ConnectRPC Python client."""
    protocol, use_binary = _CONNECT_TRANSPORTS[transport]
    codec = (
        google_protobuf_binary_codec()
        if use_binary
        else google_protobuf_json_codec()
    )
    started = time.perf_counter()
    async with ChatServiceClient(
        base_url,
        codec=codec,
        protocol=protocol,
        send_compression=None,
        timeout_ms=timeout_ms,
    ) as client:
        response = await client.say(SayRequest(text=text))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return RpcResult(
        transport=transport,
        target=base_url,
        reply=response.reply,
        elapsed_ms=elapsed_ms,
    )


async def call_rpc(
    text: str,
    *,
    transport: Transport = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> RpcResult:
    """Dispatch a ChatService.Say call to the chosen RPC transport."""
    if transport == "grpc":
        return await call_grpc(text, target=grpc_target, timeout=timeout)
    return await call_connect(
        text,
        base_url=http_url,
        transport=transport,
        timeout_ms=max(1, int(timeout * 1000)),
    )


async def stream_grpc(
    text: str,
    *,
    target: str = "127.0.0.1:50051",
    timeout: float = 5.0,
) -> AsyncIterator[ChatEvent]:
    """Yield ChatEvent messages from ChatService.StreamSay over native HTTP/2 gRPC."""
    async with grpc.aio.insecure_channel(target) as channel:
        stream = ChatServiceStub(channel).StreamSay(
            SayRequest(text=text),
            timeout=timeout,
        )
        async for event in stream:
            yield event


async def stream_connect(
    text: str,
    *,
    base_url: str = "http://127.0.0.1:8000",
    transport: ConnectTransport = "connect-binary",
    timeout_ms: int = 5000,
) -> AsyncIterator[ChatEvent]:
    """Yield ChatEvent messages from ChatService.StreamSay via ConnectRPC."""
    protocol, use_binary = _CONNECT_TRANSPORTS[transport]
    codec = (
        google_protobuf_binary_codec()
        if use_binary
        else google_protobuf_json_codec()
    )
    async with ChatServiceClient(
        base_url,
        codec=codec,
        protocol=protocol,
        send_compression=None,
        timeout_ms=timeout_ms,
    ) as client:
        async for event in client.stream_say(SayRequest(text=text)):
            yield event


async def stream_rpc(
    text: str,
    *,
    transport: Transport = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> AsyncIterator[ChatEvent]:
    """Yield ChatEvent messages from ChatService.StreamSay over the chosen transport."""
    if transport == "grpc":
        async for event in stream_grpc(text, target=grpc_target, timeout=timeout):
            yield event
        return
    async for event in stream_connect(
        text,
        base_url=http_url,
        transport=transport,
        timeout_ms=max(1, int(timeout * 1000)),
    ):
        yield event


async def collect_stream(
    text: str,
    *,
    transport: Transport = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> StreamResult:
    """Consume a StreamSay response, validating sequence order and completion."""
    target = grpc_target if transport == "grpc" else http_url
    started = time.perf_counter()
    first_delta_ms: float | None = None
    expected_sequence = 1
    events: list[ChatEvent] = []
    reply: str | None = None

    async for event in stream_rpc(
        text,
        transport=transport,
        grpc_target=grpc_target,
        http_url=http_url,
        timeout=timeout,
    ):
        if event.sequence != expected_sequence:
            raise RuntimeError(
                f"Stream sequence mismatch: expected {expected_sequence}, got {event.sequence}"
            )
        expected_sequence += 1
        events.append(event)

        kind = event.WhichOneof("payload")
        if kind == "delta" and first_delta_ms is None:
            first_delta_ms = (time.perf_counter() - started) * 1000.0
        elif kind == "complete":
            reply = event.complete.reply
        elif kind == "failure":
            raise RuntimeError(f"{event.failure.code}: {event.failure.message}")

    if reply is None:
        raise RuntimeError("Stream ended without a complete event")

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return StreamResult(
        transport=transport,
        target=target,
        events=tuple(events),
        reply=reply,
        elapsed_ms=elapsed_ms,
        first_delta_ms=first_delta_ms,
    )


async def run_demo(
    text: str,
    *,
    transport: TransportSelection = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> list[RpcResult]:
    """Execute one or all unary RPC transports for the given input text."""
    targets: tuple[Transport, ...] = (
        ALL_TRANSPORTS if transport == "all" else (transport,)
    )
    results: list[RpcResult] = []
    for item in targets:
        results.append(
            await call_rpc(
                text,
                transport=item,
                grpc_target=grpc_target,
                http_url=http_url,
                timeout=timeout,
            )
        )
    return results


async def run_stream_demo(
    text: str,
    *,
    transport: TransportSelection = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> list[StreamResult]:
    """Execute one or all server-streaming RPC transports for the given input text."""
    targets: tuple[Transport, ...] = (
        ALL_TRANSPORTS if transport == "all" else (transport,)
    )
    results: list[StreamResult] = []
    for item in targets:
        results.append(
            await collect_stream(
                text,
                transport=item,
                grpc_target=grpc_target,
                http_url=http_url,
                timeout=timeout,
            )
        )
    return results


def format_result(result: RpcResult) -> str:
    """Format a unary RPC result for terminal output."""
    return (
        f"[{result.transport}] ({result.target}, {result.elapsed_ms:.1f} ms) "
        f"reply: {result.reply}"
    )


def format_stream_result(result: StreamResult) -> str:
    """Format a streaming RPC summary for terminal output."""
    ttft = (
        f", first_delta={result.first_delta_ms:.1f} ms"
        if result.first_delta_ms is not None
        else ""
    )
    return (
        f"[{result.transport} stream] ({result.target}, {len(result.events)} events, "
        f"{result.elapsed_ms:.1f} ms{ttft}) reply: {result.reply}"
    )
