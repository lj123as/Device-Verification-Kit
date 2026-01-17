#!/usr/bin/env python3
"""
One-command launcher for DVK live streaming + JupyterLab notebook view.

Goal: minimal user actions.
- Starts dvk_live.py uart-publish (SharedMemory publisher)
- Starts JupyterLab (no browser)
- Opens live.ipynb in default browser (JupyterLab)

Note:
This repo does NOT ship Python/Jupyter binaries. Users run with their own environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import socket
from typing import Optional


def find_dvk_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def run_detached(
    args: list[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    stdout_path: Optional[Path] = None,
    stderr_path: Optional[Path] = None,
) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL
    out_f = None
    err_f = None
    try:
        if stdout_path:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            out_f = open(stdout_path, "ab")
            stdout = out_f
        if stderr_path:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            err_f = open(stderr_path, "ab")
            stderr = err_f
        p = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            env=env,
        )
    finally:
        if out_f:
            out_f.close()
        if err_f:
            err_f.close()
    return p


def _run_capture(cmd: list[str], *, cwd: Optional[Path] = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return out


def _jupyter_runtime_dir(*, python: str, cwd: Path) -> Path:
    out = _run_capture([python, "-m", "jupyter", "--runtime-dir"], cwd=cwd).strip()
    if not out:
        raise SystemExit("Could not determine Jupyter runtime dir")
    return Path(out)


def _server_info_by_pid(*, runtime_dir: Path, pid: int) -> Optional[dict]:
    for p in runtime_dir.glob("jpserver-*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(data.get("pid", -1)) == int(pid):
            return data
    return None


def _pick_free_port(start: int, *, max_tries: int = 50) -> int:
    port = int(start)
    for _ in range(max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise SystemExit(f"Could not find a free port starting from {start}")


def _load_codex_jupyter_mcp_src() -> Optional[str]:
    """
    Best-effort: read ~/.codex/config.toml and find mcp_servers.JupyterNotebook `--directory`.
    Used to add `jupyter-notebook-mcp/src` to PYTHONPATH so the bridge cell can import
    `jupyter_ws_server` without user manual sys.path changes.
    """
    try:
        config_path = Path.home() / ".codex" / "config.toml"
        if not config_path.exists():
            return None
        import tomllib  # py>=3.11

        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
        servers = cfg.get("mcp_servers") or {}
        j = servers.get("JupyterNotebook") or {}
        args = j.get("args") or []
        if not isinstance(args, list):
            return None
        for i, a in enumerate(args):
            if a == "--directory" and i + 1 < len(args):
                return str(args[i + 1])
    except Exception:
        return None
    return None


def ensure_jupyter_server(*, python: str, dvk_root: Path, timeout_s: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        out = _run_capture([python, "-m", "jupyter", "server", "list"], cwd=dvk_root)
        if "http" in out:
            return
        time.sleep(0.5)
    raise SystemExit("Jupyter server did not start in time. Try: python -m jupyter lab --no-browser")


def pick_jupyter_url(*, python: str, dvk_root: Path) -> str:
    out = _run_capture([python, "-m", "jupyter", "server", "list"], cwd=dvk_root)
    # Typical line:
    # http://localhost:8888/?token=... :: C:\path\to\dir
    for line in out.splitlines():
        if "http" not in line:
            continue
        m = re.search(r"(http://[^\s]+)", line.strip())
        if m:
            return m.group(1)
    raise SystemExit("Could not find running Jupyter server URL. Output:\n" + out.strip())


def pick_jupyter_url_for_dir(*, python: str, cwd: Path, expected_dir: Path) -> Optional[str]:
    """
    Choose a running Jupyter server whose root dir matches expected_dir.
    Returns token URL if available.
    """
    out = _run_capture([python, "-m", "jupyter", "server", "list"], cwd=cwd)
    expected = str(expected_dir.resolve())
    for line in out.splitlines():
        if "http" not in line or "::" not in line:
            continue
        parts = line.split("::", 1)
        url_part = parts[0].strip()
        dir_part = parts[1].strip()
        try:
            if str(Path(dir_part).resolve()).lower() != expected.lower():
                continue
        except Exception:
            if dir_part.lower() != expected.lower():
                continue
        m = re.search(r"(http://[^\s]+)", url_part)
        if m:
            return m.group(1)
    return None


def _split_server_url_and_token(url: str) -> tuple[str, str]:
    """
    Input examples:
      - http://localhost:8888/?token=abc
      - http://localhost:8888/lab?token=abc
    Returns:
      (server_base_url_without_path, token)
      - server base is like: http://localhost:8888
    """
    u = urlsplit(url.strip())
    base = f"{u.scheme}://{u.netloc}"
    token = ""
    try:
        token = (parse_qs(u.query).get("token") or [""])[0]
    except Exception:
        token = ""
    return base.rstrip("/"), token


def open_browser(url: str) -> None:
    # Prefer Python stdlib (handles quoting better than `cmd /c start` when URL contains `&` etc.)
    try:
        if webbrowser.open_new_tab(url):
            return
    except Exception:
        pass

    if os.name == "nt":
        # Fallback: use cmd.exe. Wrap in quotes so special characters don't break the command line.
        subprocess.Popen(
            ["cmd", "/c", "start", "", f"\"{url}\""],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    dvk_root = find_dvk_root(Path(__file__).parent)

    ap = argparse.ArgumentParser()
    ap.add_argument("--device-id", required=True)
    ap.add_argument("--workdir", help="Workdir root (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    ap.add_argument("--notebook", default="live/notebooks/live.ipynb", help="Notebook path (relative to device workdir)")
    ap.add_argument("--start-publisher", action="store_true", help="Start a SharedMemory publisher (UART -> decode -> SHM)")
    ap.add_argument("--port", help="UART port like COM22 (required with --start-publisher)")
    ap.add_argument("--baudrate", type=int, default=230400, help="UART baudrate (used with --start-publisher)")
    ap.add_argument("--protocol", help="protocol.json path (required with --start-publisher)")
    ap.add_argument("--commands", help="commands.yaml path (optional; used with --start-publisher)")
    ap.add_argument(
        "--spec-root",
        help="Private spec root (defaults to env DVK_SPEC_ROOT or $DVK_WORKDIR/Device-Verification-Kit/_assets/spec).",
    )
    ap.add_argument("--jupyter-port", type=int, default=8888)
    ap.add_argument(
        "--ui",
        choices=["auto", "lab", "nbclassic"],
        default="auto",
        help="Notebook UI. `nbclassic` is required for jupyter-notebook-mcp automation (uses Jupyter.notebook JS API).",
    )
    ap.add_argument("--no-open", action="store_true", help="Do not open browser (start services only)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--log-dir", help="Directory for logs (default: <workdir>/_logs)")
    args = ap.parse_args()

    sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, device_root, project_workdir_root  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    proj_root = project_workdir_root(workdir_root)
    dev_root = device_root(args.device_id, workdir_root=workdir_root)
    spec_root = Path(args.spec_root).expanduser().resolve() if args.spec_root else None
    log_dir = Path(args.log_dir).expanduser() if args.log_dir else (proj_root / "_logs")
    ts = time.strftime("%Y%m%d-%H%M%S")

    default_nb = "live/notebooks/live.ipynb"
    if args.notebook == default_nb:
        # Avoid clobbering an already-open notebook (Jupyter autosave can overwrite a freshly-generated file).
        nb_rel = f"live/notebooks/live_{ts}.ipynb"
        nb_out_name = Path(nb_rel).name
    else:
        nb_rel = args.notebook.format(device_id=args.device_id)
        nb_out_name = None
    nb_path = Path(nb_rel)
    if not nb_path.is_absolute():
        nb_path = (dev_root / nb_path).resolve()
    if not nb_path.exists():
        # Create live notebook template automatically (owned by live_analysis_skill).
        init_cmd = [
            sys.executable,
            str(dvk_root / "skills" / "live_analysis_skill" / "scripts" / "dvk_live_analysis.py"),
            "init",
            "--device-id",
            str(args.device_id),
            "--workdir",
            str(workdir_root),
        ]
        if nb_out_name:
            init_cmd += ["--out-name", nb_out_name]
        _run_capture(init_cmd, cwd=dvk_root)
        if not nb_path.exists():
            raise SystemExit(f"Notebook not found after init: {nb_path}")

    # 1) Start publisher (optional)
    if args.start_publisher:
        if not args.port:
            raise SystemExit("Missing --port (required with --start-publisher)")
        if not args.protocol:
            raise SystemExit("Missing --protocol (required with --start-publisher)")

        # Resolve protocol/commands from either explicit paths or ids.
        from dvk.assets import resolve_command_set, resolve_protocol  # type: ignore

        protocol_path = resolve_protocol(str(args.protocol), spec_root=spec_root)
        commands_path: Optional[Path] = None
        if args.commands:
            commands_path = resolve_command_set(str(args.commands), spec_root=spec_root)

        publisher_cmd = [
            sys.executable,
            str(dvk_root / "skills" / "transport_session_skill" / "scripts" / "dvk_live.py"),
            "uart-publish",
            "--device-id",
            str(args.device_id),
            "--port",
            str(args.port),
            "--baudrate",
            str(args.baudrate),
            "--protocol",
            str(protocol_path),
            "--overwrite-shm",
        ]
        if commands_path:
            publisher_cmd += ["--commands", str(commands_path)]
        if args.verbose:
            publisher_cmd.append("--verbose")
        pub_log = log_dir / f"publisher.{args.device_id}.{ts}.log"
        run_detached(publisher_cmd, cwd=dvk_root, stdout_path=pub_log, stderr_path=pub_log)

    # 2) Start JupyterLab (detached)
    env = os.environ.copy()
    mcp_src = env.get("JUPYTER_MCP_SRC") or _load_codex_jupyter_mcp_src()
    if mcp_src:
        cur = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (mcp_src + (os.pathsep + cur if cur else ""))
    # Choose UI: nbclassic is required for jupyter-notebook-mcp's injected client.js (uses `Jupyter.notebook`).
    ui = args.ui
    if ui == "auto":
        try:
            import importlib.util

            ui = "nbclassic" if importlib.util.find_spec("nbclassic") else "lab"
        except Exception:
            ui = "lab"

    if ui == "nbclassic":
        ui_cmd = "nbclassic"
    else:
        ui_cmd = "lab"

    # Reuse an existing server for this workdir if available (avoids token/login confusion).
    existing = pick_jupyter_url_for_dir(python=sys.executable, cwd=proj_root, expected_dir=proj_root)
    if existing:
        server_base, token = _split_server_url_and_token(existing)
        base_url = server_base + (f"/?token={token}" if token else "")
        server_url = server_base
        server_token = token
    else:
        chosen_port = _pick_free_port(int(args.jupyter_port))
        lab_cmd = [
            sys.executable,
            "-m",
            "jupyter",
            ui_cmd,
            "--no-browser",
            "--port",
            str(chosen_port),
            "--port-retries",
            "0",
            "--notebook-dir",
            str(proj_root),
        ]
        # Launch with env so notebook can import MCP bridge modules if available.
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

        jup_log = log_dir / f"jupyter.{chosen_port}.{ts}.log"
        jupyter_proc = run_detached(lab_cmd, cwd=proj_root, env=env, stdout_path=jup_log, stderr_path=jup_log)

        # Discover the actual token URL for the Jupyter process we started
        runtime_dir = _jupyter_runtime_dir(python=sys.executable, cwd=proj_root)
        info: Optional[dict] = None
        t0 = time.time()
        while time.time() - t0 < 30.0:
            info = _server_info_by_pid(runtime_dir=runtime_dir, pid=jupyter_proc.pid)
            if info:
                break
            time.sleep(0.2)

        if info:
            server_url = str(info.get("url") or "").rstrip("/")
            server_token = str(info.get("token") or "")
            base_url = f"{server_url}/?token={server_token}" if server_token else server_url
        else:
            # Fallback: sometimes the runtime json is delayed; try discovering by root-dir.
            fallback = pick_jupyter_url_for_dir(python=sys.executable, cwd=proj_root, expected_dir=proj_root)
            if not fallback:
                raise SystemExit("Failed to start a Jupyter server for the DVK workdir.")
            server_url, server_token = _split_server_url_and_token(fallback)
            base_url = server_url + (f"/?token={server_token}" if server_token else "")

    rel_from_root = nb_path.relative_to(proj_root).as_posix()
    if ui_cmd == "nbclassic":
        url = f"{server_url}/tree/{rel_from_root}"
    else:
        url = f"{server_url}/lab/tree/{rel_from_root}"
    if server_token:
        url = url + f"?token={server_token}"

    if not args.no_open:
        open_browser(url)

    print("OK")
    print(f"- workdir: {proj_root}")
    print(f"- shared_memory: dvk.{args.device_id}")
    print(f"- logs: {log_dir}")
    print(f"- jupyter: {base_url}")
    print(f"- notebook: {url}")
    if ui_cmd != "nbclassic":
        print("- note: MCP notebook automation requires nbclassic (install: pip install nbclassic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
