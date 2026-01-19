#!/usr/bin/env python3
"""
DVK ↔ embedded-memory helper CLI.

Purpose:
- Apply host-LLM generated compile_response.json back into the project-local memory store.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def find_dvk_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_memory.py", description="Apply embedded-memory compile responses in a DVK workdir")
    sub = p.add_subparsers(dest="cmd", required=True)

    apply_p = sub.add_parser("apply", help="Apply compile_response.json to profiles/candidates/overrides")
    apply_p.add_argument("--device-id", required=True)
    apply_p.add_argument("--workdir", help="Workdir root (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    apply_p.add_argument("--run-id", required=True)
    apply_p.add_argument(
        "--response",
        help="Path to compile_response.json (default: runs/<run_id>/compile_response.json under device root)",
    )
    apply_p.add_argument(
        "--request",
        help="Path to compile_request.json (default: runs/<run_id>/compile_request.json under device root)",
    )
    apply_p.set_defaults(func=cmd_apply)

    return p


def cmd_apply(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    sys.path.insert(0, str(dvk_root))

    from dvk.workdir import default_workdir_root, device_root as dvk_device_root  # type: ignore
    from dvk.memory_integration import for_device  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    device_root = dvk_device_root(args.device_id, workdir_root=workdir_root)
    run_dir = device_root / "runs" / args.run_id

    response_path = Path(args.response) if args.response else (run_dir / "compile_response.json")
    request_path = Path(args.request) if args.request else (run_dir / "compile_request.json")

    if not response_path.exists():
        raise SystemExit(f"Missing compile response: {response_path}")
    if request_path.exists():
        req = json.loads(request_path.read_text(encoding="utf-8"))
        req_id = req.get("request_id")
        print(f"Request: {request_path} (request_id={req_id})")
    else:
        request_path = None  # type: ignore[assignment]
        print("Request: (not provided)")

    mem = for_device(dvk_root=dvk_root, device_root=device_root)
    if not mem:
        raise SystemExit("embedded-memory integration not available (missing submodule or DVK_EMBEDDED_MEMORY not enabled)")

    mem.compile_apply(input_path=response_path, request_path=request_path)
    print("Applied:", response_path)


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

