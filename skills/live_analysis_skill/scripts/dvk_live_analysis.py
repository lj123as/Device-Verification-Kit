#!/usr/bin/env python3
"""
DVK LiveAnalysisSkill helper.

Responsibilities:
- Generate a live notebook that consumes DVK SharedMemory ring buffer (`dvk.<device_id>`)
- Provide a minimal, repeatable entrypoint without embedding device-specific protocol assets

This repo does NOT ship Python/Jupyter binaries; users run this with their own environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def find_dvk_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def _md_cell(text: str) -> Dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def _code_cell(code: str) -> Dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}


def build_live_notebook(*, device_id: str, dvk_code_root: Path) -> Dict[str, Any]:
    bridge = """# JupyterNotebook MCP bridge (run once per notebook session)
# This enables Codex tools like `JupyterNotebook.run_cell` / `run_all_cells`.
#
# Requirements:
# - You installed/enabled `jupyter-notebook-mcp` (MCP server).
# - You opened this notebook in nbclassic (not JupyterLab), because the injected JS uses `Jupyter.notebook`.
#
# If import fails, ensure `jupyter-notebook-mcp/src` is importable by the notebook kernel.
try:
    from jupyter_ws_server import setup_jupyter_mcp_integration  # type: ignore
    server, port = setup_jupyter_mcp_integration()
    print(f"Jupyter MCP bridge ready: {server}:{port}")
except Exception as e:
    print("Jupyter MCP bridge not available:", repr(e))
    print("Fix: ensure `jupyter-notebook-mcp/src` is on PYTHONPATH for this kernel, then restart the notebook server.")
"""

    live = f"""import time
import numpy as np
from IPython.display import display
import sys
from pathlib import Path

DVK_CODE_ROOT = Path(r\"{str(dvk_code_root.resolve())}\")
sys.path.insert(0, str(DVK_CODE_ROOT))

from dvk.shm import attach_ring, read_latest

BASE = 'dvk.{device_id}'

def wait_attach(name: str, timeout_s: float = 30.0, poll_s: float = 0.2):
    t0 = time.time()
    last_err = None
    while time.time() - t0 < timeout_s:
        try:
            return attach_ring(name)
        except FileNotFoundError as e:
            last_err = e
            time.sleep(poll_s)
    raise RuntimeError(
        f"SharedMemory '{{name}}' not found (waited {{timeout_s}}s). "
        "Start a publisher to create it, then retry."
    ) from last_err

h = wait_attach(BASE)

MAX_POINTS = 20000
FPS = 6

# If the publisher restarts with --overwrite-shm, the consumer may hold stale SHM handles.
# We re-attach when the writer's seq/last_write_ns stops moving for a while.
stale_ticks = 0
last_seq_seen = -1
last_ns_seen = -1

# Preferred: Plotly (mature, WebGL Scattergl). Fallback: matplotlib.
try:
    import plotly.graph_objects as go

    fig = go.FigureWidget(
        data=[
            go.Scattergl(x=[], y=[], mode='markers', marker=dict(size=2))
        ],
        layout=go.Layout(
            title='Live 2D point cloud',
            xaxis=dict(scaleanchor='y', scaleratio=1),
            yaxis=dict(),
            margin=dict(l=20, r=20, t=40, b=20),
        ),
    )
    display(fig)

    for _ in range(10_000):
        seq = int(h.ctrl['seq'][0])
        ns = int(h.ctrl['last_write_ns'][0])
        if seq == last_seq_seen and ns == last_ns_seen:
            stale_ticks += 1
        else:
            stale_ticks = 0
            last_seq_seen, last_ns_seen = seq, ns
        if stale_ticks >= int(FPS * 2):
            try:
                h = attach_ring(BASE)
            except Exception:
                pass
            stale_ticks = 0

        pts = read_latest(h, MAX_POINTS)
        if len(pts) > 0:
            with fig.batch_update():
                fig.data[0].x = pts['x'].astype(float)
                fig.data[0].y = pts['y'].astype(float)
                fig.layout.title = f'Live 2D point cloud (n={{len(pts)}}, seq={{seq}})'
                fig.layout.xaxis.autorange = True
                fig.layout.yaxis.autorange = True
        else:
            with fig.batch_update():
                fig.data[0].x = []
                fig.data[0].y = []
                fig.layout.title = f'Live 2D point cloud (waiting..., seq={{seq}})'
        time.sleep(1.0 / FPS)
except Exception:
    import matplotlib.pyplot as plt

    # If you have ipympl installed, widget backend may improve smoothness.
    try:
        get_ipython().run_line_magic('matplotlib', 'widget')
    except Exception:
        pass

    plt.ioff()
    fig, ax = plt.subplots(figsize=(7,7))
    sc = ax.scatter([], [], s=1)
    ax.set_aspect('equal', adjustable='box')
    ax.grid(True)
    handle = display(fig, display_id=True)

    last_seq = -1
    for _ in range(10_000):
        seq = int(h.ctrl['seq'][0])
        ns = int(h.ctrl['last_write_ns'][0])
        if seq == last_seq_seen and ns == last_ns_seen:
            stale_ticks += 1
        else:
            stale_ticks = 0
            last_seq_seen, last_ns_seen = seq, ns
        if stale_ticks >= int(FPS * 2):
            try:
                h = attach_ring(BASE)
            except Exception:
                pass
            stale_ticks = 0

        pts = read_latest(h, MAX_POINTS)
        if len(pts) > 0:
            xs = pts["x"].astype(float)
            ys = pts["y"].astype(float)
            sc.set_offsets(np.c_[xs, ys])
            ax.set_title(f'Live 2D point cloud (n={{len(pts)}}, seq={{seq}})')
            xmin, xmax = float(np.min(xs)), float(np.max(xs))
            ymin, ymax = float(np.min(ys)), float(np.max(ys))
            span = max(xmax - xmin, ymax - ymin)
            pad = span * 0.05
            if not np.isfinite(pad) or pad <= 0:
                pad = 1.0
            ax.set_xlim(xmin - pad, xmax + pad)
            ax.set_ylim(ymin - pad, ymax + pad)
        else:
            sc.set_offsets(np.zeros((0, 2), dtype=np.float32))
            ax.set_title(f'Live 2D point cloud (waiting..., seq={{seq}})')

        if seq != last_seq:
            handle.update(fig)
            last_seq = seq

        time.sleep(1.0 / FPS)
"""

    cells: List[Dict[str, Any]] = [
        _md_cell(
            "# DVK Live Analysis\n\n"
            f"- device_id: `{device_id}`\n"
            f"- shared_memory: `dvk.{device_id}`\n\n"
            "This notebook is a live viewer. It does not connect to devices.\n"
            "Upstream should publish semantic point rows to SharedMemory.\n"
        ),
        _code_cell(bridge),
        _md_cell("## Diagnostics\n\nRun the cell below to verify that the notebook reads non-zero points from SharedMemory."),
        _code_cell(
            f"""import sys
from pathlib import Path
import numpy as np

DVK_CODE_ROOT = Path(r\"{str(dvk_code_root.resolve())}\")
sys.path.insert(0, str(DVK_CODE_ROOT))

import dvk.shm as dvk_shm
from dvk.shm import attach_ring, read_latest

print('dvk_shm:', dvk_shm.__file__)
h = attach_ring('dvk.{device_id}')
pts = read_latest(h, 20000)
print('seq', int(h.ctrl['seq'][0]), 'last_write_ns', int(h.ctrl['last_write_ns'][0]), 'n', len(pts))
x = pts['x'].astype(float)
y = pts['y'].astype(float)
print('x[min,max,std]', float(np.min(x)), float(np.max(x)), float(np.std(x)))
print('y[min,max,std]', float(np.min(y)), float(np.max(y)), float(np.std(y)))
print('x==0 %', float(np.mean(x==0))*100.0)
"""
        ),
        _md_cell("## Live View (SharedMemory)\n\nRun the cell below to view live 2D point cloud."),
        _code_cell(live),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": sys.version.split()[0]},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def cmd_init(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, device_root  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    nb = build_live_notebook(device_id=args.device_id, dvk_code_root=dvk_root)
    out_name = str(args.out_name or "live.ipynb")
    out = device_root(args.device_id, workdir_root=workdir_root) / "live" / "notebooks" / out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(str(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="Generate live.ipynb")
    p_init.add_argument("--device-id", required=True)
    p_init.add_argument("--workdir", help="Workdir root (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    p_init.add_argument("--out-name", dest="out_name", help="Notebook file name under <device>/live/notebooks/")
    p_init.set_defaults(func=cmd_init)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
