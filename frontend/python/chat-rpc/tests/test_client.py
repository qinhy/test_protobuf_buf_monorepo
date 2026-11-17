"""Unit and integration tests for the standalone RPC demo client."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys

import pytest

CLIENT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = CLIENT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

RPC_STUB = CLIENT_ROOT / "src/chat/v1/chat_pb2.py"


@pytest.mark.skipif(not RPC_STUB.is_file(), reason="Run scripts/generate.py first")
def test_cli_single_shot_and_interactive(monkeypatch, capsys):
    from chat_rpc.cli import main
    from chat_rpc.client import RpcResult

    recorded: list[tuple[str, str]] = []

    async def fake_run_demo(text, *, transport="grpc", **kwargs):
        recorded.append((transport, text))
        return [
            RpcResult(
                transport="grpc" if transport == "all" else transport,
                target="127.0.0.1:50051",
                reply="demo reply",
                elapsed_ms=1.5,
            )
        ]

    monkeypatch.setattr("chat_rpc.cli.run_demo", fake_run_demo)

    assert main(["--transport", "grpc", "--text", "ping"]) == 0
    out = capsys.readouterr().out
    assert "you> ping" in out
    assert "[grpc] (127.0.0.1:50051, 1.5 ms) reply: demo reply" in out

    inputs = iter(["hello rpc", "   ", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    assert main(["--interactive", "--transport", "connect-binary"]) == 0
    assert recorded == [
        ("grpc", "ping"),
        ("connect-binary", "hello rpc"),
    ]


@pytest.mark.skipif(not RPC_STUB.is_file(), reason="Run scripts/generate.py first")
def test_cli_connection_error(monkeypatch, capsys):
    import grpc
    from chat_rpc.cli import main

    async def fail_demo(*args, **kwargs):
        raise grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Connection refused",
        )

    monkeypatch.setattr("chat_rpc.cli.run_demo", fail_demo)
    assert main(["--transport", "grpc"]) == 1
    assert "chat-server" in capsys.readouterr().err


@asynccontextmanager
async def _local_echo_grpc_server():
    import grpc
    from chat.v1.chat_pb2 import SayResponse
    from chat.v1.chat_pb2_grpc import (
        ChatServiceServicer,
        add_ChatServiceServicer_to_server,
    )

    class EchoServicer(ChatServiceServicer):
        async def Say(self, request, context):
            return SayResponse(reply=f"echo:{request.text}")

    server = grpc.aio.server()
    add_ChatServiceServicer_to_server(EchoServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    await server.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        await server.stop(grace=0.5)


@pytest.mark.skipif(not RPC_STUB.is_file(), reason="Run scripts/generate.py first")
def test_call_grpc_against_local_stub_server():
    from chat_rpc.client import call_grpc

    async def exercise() -> None:
        async with _local_echo_grpc_server() as target:
            result = await call_grpc("hello", target=target)
            assert result.transport == "grpc"
            assert result.target == target
            assert result.reply == "echo:hello"
            assert result.elapsed_ms >= 0.0

    asyncio.run(exercise())
