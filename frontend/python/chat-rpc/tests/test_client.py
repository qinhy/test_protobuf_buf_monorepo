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
    from chat_rpc.client import RpcResult, StreamResult

    recorded: list[tuple[str, str, str]] = []

    async def fake_run_demo(text, *, transport="grpc", **kwargs):
        recorded.append(("unary", transport, text))
        return [
            RpcResult(
                transport="grpc" if transport == "all" else transport,
                target="127.0.0.1:50051",
                reply="demo reply",
                elapsed_ms=1.5,
            )
        ]

    async def fake_run_stream_demo(text, *, transport="grpc", **kwargs):
        recorded.append(("stream", transport, text))
        return [
            StreamResult(
                transport="grpc" if transport == "all" else transport,
                target="127.0.0.1:50051",
                events=(),
                reply="stream reply",
                elapsed_ms=4.2,
                first_delta_ms=1.1,
            )
        ]

    monkeypatch.setattr("chat_rpc.cli.run_demo", fake_run_demo)
    monkeypatch.setattr("chat_rpc.cli.run_stream_demo", fake_run_stream_demo)

    assert main(["--transport", "grpc", "--text", "ping"]) == 0
    out = capsys.readouterr().out
    assert "you> ping" in out
    assert "[grpc] (127.0.0.1:50051, 1.5 ms) reply: demo reply" in out

    assert main(["--stream", "--transport", "connect-binary", "--text", "ping-stream"]) == 0
    stream_out = capsys.readouterr().out
    assert "[connect-binary stream]" in stream_out
    assert "reply: stream reply" in stream_out

    inputs = iter(["hello rpc", "   ", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    assert main(["--interactive", "--transport", "connect-binary"]) == 0
    assert recorded == [
        ("unary", "grpc", "ping"),
        ("stream", "connect-binary", "ping-stream"),
        ("unary", "connect-binary", "hello rpc"),
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
    from chat.v1.chat_pb2 import (
        ChatComplete,
        ChatDelta,
        ChatEvent,
        ChatStart,
        SayResponse,
    )
    from chat.v1.chat_pb2_grpc import (
        ChatServiceServicer,
        add_ChatServiceServicer_to_server,
    )

    class EchoServicer(ChatServiceServicer):
        async def Say(self, request, context):
            return SayResponse(reply=f"echo:{request.text}")

        async def StreamSay(self, request, context):
            full = f"echo:{request.text}"
            yield ChatEvent(sequence=1, start=ChatStart(message_id="msg-1"))
            yield ChatEvent(sequence=2, delta=ChatDelta(text="echo:"))
            yield ChatEvent(sequence=3, delta=ChatDelta(text=request.text))
            yield ChatEvent(sequence=4, complete=ChatComplete(reply=full))

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
def test_call_and_stream_grpc_against_local_stub_server():
    from chat_rpc.client import call_grpc, collect_stream

    async def exercise() -> None:
        async with _local_echo_grpc_server() as target:
            result = await call_grpc("hello", target=target)
            assert result.transport == "grpc"
            assert result.target == target
            assert result.reply == "echo:hello"
            assert result.elapsed_ms >= 0.0

            stream_result = await collect_stream("hello", transport="grpc", grpc_target=target)
            assert stream_result.transport == "grpc"
            assert stream_result.reply == "echo:hello"
            assert len(stream_result.events) == 4
            assert [e.sequence for e in stream_result.events] == [1, 2, 3, 4]

    asyncio.run(exercise())
