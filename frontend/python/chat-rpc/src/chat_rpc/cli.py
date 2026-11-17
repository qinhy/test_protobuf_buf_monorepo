"""CLI entry point for the native gRPC / ConnectRPC demo client."""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import os
import sys

from connectrpc.errors import ConnectError
import grpc

from chat_rpc.client import (
    ALL_TRANSPORTS,
    format_result,
    format_stream_result,
    run_demo,
    run_stream_demo,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the native RPC demo client."""
    parser = argparse.ArgumentParser(
        prog="chat-rpc-demo",
        description="Call ChatService.Say or StreamSay using generated native gRPC / ConnectRPC clients.",
    )
    parser.add_argument(
        "--transport",
        choices=(*ALL_TRANSPORTS, "all"),
        default="grpc",
        help="RPC transport to use (default: grpc).",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use server-streaming ChatService.StreamSay instead of unary Say.",
    )
    parser.add_argument(
        "--text",
        default="Hello from native RPC client!",
        help="Message text to send in single-shot mode.",
    )
    parser.add_argument(
        "--grpc-target",
        default=os.environ.get("GRPC_TARGET", "127.0.0.1:50051"),
        help="Native gRPC host:port target (default: 127.0.0.1:50051).",
    )
    parser.add_argument(
        "--http-url",
        default=os.environ.get("CHAT_HTTP_URL", "http://127.0.0.1:8000"),
        help="ConnectRPC / gRPC-Web base URL (default: http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Start an interactive prompt instead of sending a single message.",
    )
    return parser


async def _dispatch(args: argparse.Namespace, text: str) -> None:
    if args.stream:
        results = await run_stream_demo(
            text,
            transport=args.transport,
            grpc_target=args.grpc_target,
            http_url=args.http_url,
            timeout=args.timeout,
        )
        for result in results:
            print(format_stream_result(result))
        return

    results = await run_demo(
        text,
        transport=args.transport,
        grpc_target=args.grpc_target,
        http_url=args.http_url,
        timeout=args.timeout,
    )
    for result in results:
        print(format_result(result))


async def _run_interactive(args: argparse.Namespace) -> None:
    mode = "stream" if args.stream else "unary"
    print(
        f"Native RPC interactive mode (transport={args.transport}, mode={mode}). "
        "Type a message, or 'exit' / Ctrl+C to quit."
    )
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        await _dispatch(args, text)


async def _run_cli(args: argparse.Namespace) -> None:
    if args.interactive:
        await _run_interactive(args)
        return
    print(f"you> {args.text}")
    await _dispatch(args, args.text)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `uv run chat-rpc-demo`."""
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(_run_cli(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except (grpc.aio.AioRpcError, ConnectError, OSError) as exc:
        print(
            f"[FAIL] RPC request failed ({type(exc).__name__}): {exc}\n"
            "Make sure the backend is running (`uv run chat-server` in backend/python/chat).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
