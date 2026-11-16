"""Expose Buf-generated Python namespaces without copying generated files.

This is demo bootstrapping only. In a larger project, package the generated
Protobuf code as its own installable Python distribution.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN_PYTHON = ROOT / "gen" / "python"
if not (GEN_PYTHON / "chat" / "v1" / "chat_pb2.py").exists():
    raise RuntimeError(
        "Generated Protobuf Python files are missing. Run `buf generate` "
        "from the repository root first."
    )
if str(GEN_PYTHON) not in sys.path:
    sys.path.insert(0, str(GEN_PYTHON))
