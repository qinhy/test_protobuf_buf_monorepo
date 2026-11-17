"""Native gRPC and ConnectRPC client calls built from generated chat.v1 stubs."""
from __future__ import annotations

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
from chat.v1.chat_pb2 import SayRequest
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
    """Result returned by a single RPC invocation."""

    transport: Transport
    target: str
    reply: str
    elapsed_ms: float


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


async def run_demo(
    text: str,
    *,
    transport: TransportSelection = "grpc",
    grpc_target: str = "127.0.0.1:50051",
    http_url: str = "http://127.0.0.1:8000",
    timeout: float = 5.0,
) -> list[RpcResult]:
    """Execute one or all native RPC transports for the given input text."""
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


def format_result(result: RpcResult) -> str:
    """Format an RPC result for terminal output."""
    return (
        f"[{result.transport}] ({result.target}, {result.elapsed_ms:.1f} ms) "
        f"reply: {result.reply}"
    )
