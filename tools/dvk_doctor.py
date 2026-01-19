#!/usr/bin/env python3
"""
DVK environment & setup checks.

Goal: make "real device test" predictable by validating:
- Python interpreter path/version
- Required Python deps per workflow (offline / live / notebook)
- DVK default workdir/spec roots
- Optional: COM port availability (best-effort, non-invasive)
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def _find_dvk_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


@dataclass(frozen=True)
class DoctorResult:
    ok: bool
    details: str


def _try_import(mod: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(mod)
        return True, ""
    except Exception as e:
        return False, str(e)


def _readable_path(p: Path) -> str:
    try:
        return str(p.resolve())
    except Exception:
        return str(p)


def check_paths(*, dvk_root: Path, device_id: Optional[str], model_id: Optional[str]) -> DoctorResult:
    sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, device_root, project_workdir_root  # type: ignore

    workdir_root = default_workdir_root()
    proj_root = project_workdir_root(workdir_root)
    _ok(f"DVK_WORKDIR default: {_readable_path(workdir_root)}")
    _ok(f"Project workdir: {_readable_path(proj_root)}")
    if device_id:
        _ok(f"Device workdir: {_readable_path(device_root(device_id, workdir_root=workdir_root))}")

    from dvk.assets import default_spec_root, resolve_model  # type: ignore

    spec_root = default_spec_root()
    if spec_root.exists():
        _ok(f"Spec root: {_readable_path(spec_root)}")
    else:
        _warn(f"Spec root does not exist yet: {_readable_path(spec_root)}")

    if model_id:
        try:
            mp = resolve_model(model_id)
            _ok(f"Model found: {model_id} -> {_readable_path(mp)}")
        except Exception as e:
            _fail(f"Model not found: {model_id} ({e})")
            return DoctorResult(ok=False, details="model missing")

    return DoctorResult(ok=True, details="paths ok")


def check_deps(*, want_live: bool, want_notebook: bool, want_mcp: bool, want_uart: bool, want_model_yaml: bool) -> DoctorResult:
    ok = True
    # Core
    for mod, pip in [
        ("numpy", "numpy"),
    ]:
        has, err = _try_import(mod)
        if has:
            _ok(f"import {mod}")
        else:
            ok = False
            _fail(f"import {mod} failed: {err} (pip install {pip})")

    if want_uart:
        has, err = _try_import("serial")
        if has:
            _ok("import pyserial")
        else:
            ok = False
            _fail(f"import serial failed: {err} (pip install pyserial)")

    if want_model_yaml:
        has, err = _try_import("yaml")
        if has:
            _ok("import pyyaml")
        else:
            ok = False
            _fail(f"import yaml failed: {err} (pip install pyyaml)")

    if want_live:
        has, err = _try_import("plotly")
        if has:
            _ok("import plotly (live notebook)")
        else:
            ok = False
            _fail(f"import plotly failed: {err} (pip install plotly)")

    if want_notebook:
        has, err = _try_import("jupyter_server")
        if has:
            _ok("import jupyter_server")
        else:
            ok = False
            _fail(f"import jupyter_server failed: {err} (pip install jupyter)")

    if want_mcp:
        has, err = _try_import("nbclassic")
        if has:
            _ok("import nbclassic (required for notebook MCP automation)")
        else:
            _warn(f"nbclassic not installed: {err} (pip install nbclassic)")

    return DoctorResult(ok=ok, details="deps ok" if ok else "deps missing")


def check_serial_port(*, port: Optional[str]) -> DoctorResult:
    if not port:
        return DoctorResult(ok=True, details="no port check")

    try:
        from serial.tools import list_ports  # type: ignore

        ports = [p.device for p in list_ports.comports()]
        if ports:
            _ok(f"Serial ports detected: {', '.join(ports)}")
        else:
            _warn("No serial ports detected by pyserial")
        if port not in ports:
            _warn(f"Requested port not in detected list: {port}")
    except Exception as e:
        _warn(f"pyserial list_ports unavailable: {e}")

    # Best-effort open/close (non-invasive): quick open, no read.
    try:
        import serial  # type: ignore

        with serial.Serial(port=port, baudrate=115200, timeout=0.1) as _:
            _ok(f"Serial port open OK: {port} (baudrate probe 115200)")
        return DoctorResult(ok=True, details="port ok")
    except Exception as e:
        _warn(f"Serial port open failed (may be busy/in use): {port} ({e})")
        return DoctorResult(ok=True, details="port open warn")


def main() -> int:
    ap = argparse.ArgumentParser(prog="dvk_doctor.py", description="DVK environment checks")
    ap.add_argument("--device-id", help="Device instance id (used for workdir paths)")
    ap.add_argument("--model-id", help="Model id (validates model yaml exists)")
    ap.add_argument("--port", help="Serial port to check (e.g. COM22)")
    ap.add_argument("--mode", choices=["offline", "live", "live-mcp"], default="offline")
    args = ap.parse_args()

    print("DVK Doctor")
    _ok(f"python: {sys.executable}")
    _ok(f"python_version: {sys.version.split()[0]}")
    if os.environ.get("VIRTUAL_ENV"):
        _ok(f"venv: {os.environ['VIRTUAL_ENV']}")
    else:
        _warn("No VIRTUAL_ENV detected (you may be using global Python)")

    dvk_root = _find_dvk_root(Path(__file__).parent)

    want_live = args.mode in ("live", "live-mcp")
    want_notebook = args.mode in ("live", "live-mcp")
    want_mcp = args.mode == "live-mcp"
    want_uart = True
    want_model_yaml = bool(args.model_id)

    deps = check_deps(
        want_live=want_live,
        want_notebook=want_notebook,
        want_mcp=want_mcp,
        want_uart=want_uart,
        want_model_yaml=want_model_yaml,
    )
    paths = check_paths(dvk_root=dvk_root, device_id=args.device_id, model_id=args.model_id)
    check_serial_port(port=args.port)

    if deps.ok and paths.ok:
        _ok("Doctor summary: OK")
        return 0
    _fail("Doctor summary: FAIL (see messages above)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

