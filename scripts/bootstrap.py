"""Regenerate every artifact from proto/chat/v1/chat.proto.

Prerequisites: pip dependencies installed, Buf CLI, Node.js and npm.
Example: python scripts/bootstrap.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args, cwd=ROOT):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def main():
    for cmd in ("buf", "node", "npm"):
        if not shutil.which(cmd):
            raise SystemExit(f"Missing '{cmd}'. Install it before running bootstrap.")
    run("buf", "lint")
    run("buf", "generate")
    run(sys.executable, "-m", "backend.export_openapi")
    run("npm", "install", cwd=ROOT / "frontend")
    run("npm", "run", "generate:rest", cwd=ROOT / "frontend")
    print("\nGeneration complete. Start uvicorn and the Vite dev server.")


if __name__ == "__main__":
    main()
