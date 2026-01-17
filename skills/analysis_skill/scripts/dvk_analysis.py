#!/usr/bin/env python3
"""
DVK AnalysisSkill runnable scaffold.

This repo does NOT ship Python/Jupyter binaries. Users run this with their own environment.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_dvk_root(start: Path) -> Path:
    """Find DVK root by locating .claude-plugin/plugin.json marker file."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def detect_decoded_input(dvk_root: Path, device_id: str) -> Optional[Path]:
    base = dvk_root / "data" / "processed" / device_id
    candidates = [
        base / "decoded.parquet",
        base / "decoded.csv",
        base / "decoded.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def notebook_template(
    template: str,
    device_id: str,
    decoded_path: str,
    *,
    dvk_code_root: Path,
    analysis_dir: Path,
    processed_dir: Path,
) -> Dict[str, Any]:
    figures_dir = analysis_dir / "figures"
    cleaned_path = processed_dir / "cleaned.parquet"
    metrics_path = analysis_dir / "metrics.csv"
    anomalies_path = analysis_dir / "anomalies.csv"

    def md_cell(source: str) -> Dict[str, Any]:
        return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}

    def code_cell(source: str) -> Dict[str, Any]:
        return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": source.splitlines(True)}

    base_cells: List[Dict[str, Any]] = [
        md_cell(
            f"# DVK Analysis ({template})\n\n"
            f"- device_id: `{device_id}`\n"
            f"- input: `{decoded_path}`\n"
            f"- figures_dir: `{figures_dir}`\n"
        ),
        md_cell("## 0) Setup"),
        code_cell(
            "import pandas as pd\n"
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns\n"
            "from pathlib import Path\n"
            "sns.set_theme(style='whitegrid')\n"
        ),
        code_cell(
            f"INPUT = r\"{decoded_path}\"\n"
            f"FIG_DIR = Path(r\"{str(figures_dir)}\")\n"
            "FIG_DIR.mkdir(parents=True, exist_ok=True)\n"
            "INPUT\n"
        ),
        md_cell("## 1) Load data"),
        code_cell(
            "if INPUT.lower().endswith('.parquet'):\n"
            "    df = pd.read_parquet(INPUT)\n"
            "elif INPUT.lower().endswith('.csv'):\n"
            "    df = pd.read_csv(INPUT)\n"
            "else:\n"
            "    df = pd.read_json(INPUT, lines=False)\n"
            "df.head()\n"
        ),
    ]

    eda_cells: List[Dict[str, Any]] = [
        md_cell("## EDA: basic profiling"),
        code_cell(
            "df.shape\n"
            "\n"
            "df.dtypes\n"
            "\n"
            "df.isna().mean().sort_values(ascending=False).head(20)\n"
        ),
        md_cell("## EDA: distributions (choose key columns)"),
        code_cell(
            "NUM_COLS = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]\n"
            "NUM_COLS[:10]\n"
        ),
        code_cell(
            "col = NUM_COLS[0] if NUM_COLS else None\n"
            "if col:\n"
            "    plt.figure(figsize=(10,4))\n"
            "    sns.histplot(df[col].dropna(), kde=True)\n"
            "    plt.title(col)\n"
            "    out = FIG_DIR / f\"hist_{col}.png\"\n"
            "    plt.savefig(out, dpi=160, bbox_inches='tight')\n"
            "    plt.show()\n"
            "    out\n"
        ),
    ]

    cleaning_cells: List[Dict[str, Any]] = [
        md_cell("## Cleaning: define rules (do not guess)"),
        md_cell(
            "- Missing values: drop/fill?\n"
            "- Outliers: tag vs remove?\n"
            "- Duplicates: which keys?\n"
            "- Time alignment: which column is time?\n"
        ),
        code_cell(
            "# TODO: implement your cleaning rules here\n"
            "df_clean = df.copy()\n"
            "df_clean.head()\n"
        ),
        md_cell("## Cleaning: save cleaned dataset"),
        code_cell(
            f"CLEANED_OUT = r\"{str(cleaned_path)}\"\n"
            "Path(CLEANED_OUT).parent.mkdir(parents=True, exist_ok=True)\n"
            "df_clean.to_parquet(CLEANED_OUT, index=False)\n"
            "CLEANED_OUT\n"
        ),
    ]

    metrics_cells: List[Dict[str, Any]] = [
        md_cell("## Metrics: load cleaned dataset if available"),
        code_cell(
            f"CLEANED = r\"{str(cleaned_path)}\"\n"
            "if Path(CLEANED).exists():\n"
            "    dfm = pd.read_parquet(CLEANED)\n"
            "else:\n"
            "    dfm = df\n"
            "dfm.shape\n"
        ),
        md_cell("## Metrics: define metrics + thresholds (do not guess)"),
        code_cell(
            "# Example: mean/std for numeric columns\n"
            "num_cols = [c for c in dfm.columns if pd.api.types.is_numeric_dtype(dfm[c])]\n"
            "summary = dfm[num_cols].describe().T\n"
            "summary.head()\n"
        ),
        md_cell("## Metrics: export"),
        code_cell(
            f"METRICS_OUT = r\"{str(metrics_path)}\"\n"
            "Path(METRICS_OUT).parent.mkdir(parents=True, exist_ok=True)\n"
            "summary.to_csv(METRICS_OUT)\n"
            "METRICS_OUT\n"
        ),
    ]

    anomaly_cells: List[Dict[str, Any]] = [
        md_cell("## Anomaly detection: pick signals + definition"),
        code_cell(
            "# TODO: define anomaly rules. Example below: z-score on a chosen column\n"
            "num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]\n"
            "target = num_cols[0] if num_cols else None\n"
            "target\n"
        ),
        code_cell(
            "if target:\n"
            "    s = df[target].astype(float)\n"
            "    z = (s - s.mean()) / (s.std() + 1e-12)\n"
            "    anomalies = df.loc[z.abs() > 5].copy()\n"
            "else:\n"
            "    anomalies = df.iloc[0:0].copy()\n"
            "anomalies.head()\n"
        ),
        md_cell("## Anomaly detection: export list"),
        code_cell(
            f"ANOM_OUT = r\"{str(anomalies_path)}\"\n"
            "Path(ANOM_OUT).parent.mkdir(parents=True, exist_ok=True)\n"
            "anomalies.to_csv(ANOM_OUT, index=False)\n"
            "ANOM_OUT\n"
        ),
    ]

    viz_cells: List[Dict[str, Any]] = [
        md_cell("## Visualization: time series / correlations (choose columns)"),
        code_cell(
            "num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]\n"
            "num_cols[:10]\n"
        ),
        code_cell(
            "if len(num_cols) >= 2:\n"
            "    x, y = num_cols[0], num_cols[1]\n"
            "    plt.figure(figsize=(6,6))\n"
            "    sns.scatterplot(data=df, x=x, y=y, s=10)\n"
            "    out = FIG_DIR / f\"scatter_{x}_{y}.png\"\n"
            "    plt.savefig(out, dpi=160, bbox_inches='tight')\n"
            "    plt.show()\n"
            "    out\n"
        ),
    ]

    templates: Dict[str, List[Dict[str, Any]]] = {
        "eda": eda_cells,
        "cleaning": cleaning_cells,
        "metrics": metrics_cells,
        "anomaly": anomaly_cells,
        "viz": viz_cells,
        "full": eda_cells + cleaning_cells + metrics_cells + anomaly_cells + viz_cells,
    }

    cells = base_cells + templates.get(template, eda_cells)

    return {
        "cells": [
            *cells
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": sys.version.split()[0]},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def cmd_check_env(_: argparse.Namespace) -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    report: Dict[str, Any] = {
        "python": sys.executable,
        "python_version": sys.version.splitlines()[0],
        "platform": platform.platform(),
        "packages": {},
        "jupyter": {},
    }

    required = ["pandas", "numpy", "matplotlib", "seaborn", "jupyter"]
    for mod in required:
        try:
            __import__(mod)
            report["packages"][mod] = "ok"
        except Exception as e:
            report["packages"][mod] = f"missing: {e}"

    jupyter_bin = shutil.which("jupyter")
    report["jupyter"]["bin"] = jupyter_bin
    if jupyter_bin:
        try:
            out = subprocess.check_output([jupyter_bin, "--version"], stderr=subprocess.STDOUT, text=True)
            report["jupyter"]["version"] = out.strip()
        except Exception as e:
            report["jupyter"]["version_error"] = str(e)
    else:
        # On Windows, `python -m jupyter` may work even if `jupyter.exe` isn't on PATH.
        try:
            out = subprocess.check_output([sys.executable, "-m", "jupyter", "--version"], stderr=subprocess.STDOUT, text=True)
            report["jupyter"]["python_module_version"] = out.strip()
        except Exception as e:
            report["jupyter"]["python_module_version_error"] = str(e)

    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_init(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    # Private workdir (default): %USERPROFILE%/DVK_Workspaces
    sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, latest_run_id, run_paths  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if getattr(args, "workdir", None) else default_workdir_root()
    effective_run_id = getattr(args, "run_id", None) or latest_run_id(device_id, workdir_root=workdir_root)
    run = run_paths(device_id, run_id=effective_run_id, workdir_root=workdir_root)

    decoded = Path(args.input) if args.input else None
    if decoded is None:
        candidates = [
            run.processed_dir / "decoded.parquet",
            run.processed_dir / "decoded.csv",
            run.processed_dir / "decoded.json",
        ]
        decoded = next((c for c in candidates if c.exists()), None) or detect_decoded_input(dvk_root, device_id)
    if decoded is None:
        raise SystemExit(
            "Decoded input not found. Provide --input or create one of:\n"
            f"  {run.processed_dir / 'decoded.parquet'}\n"
            f"  {run.processed_dir / 'decoded.csv'}\n"
            f"  {run.processed_dir / 'decoded.json'}\n"
        )

    analysis_dir = run.reports_dir / "analysis"
    notebooks_dir = analysis_dir / "notebooks"
    figures_dir = analysis_dir / "figures"
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    template = args.template
    nb_name_map = {
        "eda": "eda.ipynb",
        "cleaning": "cleaning.ipynb",
        "metrics": "metrics.ipynb",
        "anomaly": "anomaly.ipynb",
        "viz": "viz.ipynb",
        "full": "analysis_full.ipynb",
    }
    nb_path = notebooks_dir / nb_name_map.get(template, "eda.ipynb")
    if nb_path.exists() and not args.overwrite:
        raise SystemExit(f"Notebook already exists: {nb_path} (use --overwrite)")

    nb = notebook_template(
        template=template,
        device_id=device_id,
        decoded_path=str(decoded.resolve()),
        dvk_code_root=dvk_root,
        analysis_dir=analysis_dir,
        processed_dir=run.processed_dir,
    )
    nb_path.write_text(json.dumps(nb, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = analysis_dir / "summary.md"
    if not summary.exists():
        write_text(
            summary,
            f"# DVK Analysis Summary\n\n- device_id: `{device_id}`\n- created_at: `{datetime.now().isoformat(timespec='seconds')}`\n- input: `{decoded}`\n\n## Findings\n\n- \n",
        )

    print(str(nb_path))


def cmd_launch(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, latest_run_id, run_paths  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if getattr(args, "workdir", None) else default_workdir_root()
    effective_run_id = getattr(args, "run_id", None) or latest_run_id(device_id, workdir_root=workdir_root)
    run = run_paths(device_id, run_id=effective_run_id, workdir_root=workdir_root)

    notebooks_dir = run.reports_dir / "analysis" / "notebooks"
    notebooks_dir.mkdir(parents=True, exist_ok=True)

    jupyter_bin = shutil.which("jupyter")
    if jupyter_bin:
        cmd: List[str] = [jupyter_bin, args.mode]
    else:
        # Fallback: run jupyter as a module from the active python environment.
        cmd = [sys.executable, "-m", "jupyter", args.mode]
    if args.port:
        cmd += ["--port", str(args.port)]
    if args.no_browser:
        cmd += ["--no-browser"]

    print(f"Launching in: {notebooks_dir}")
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(notebooks_dir))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_analysis.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check-env", help="Check Python/Jupyter environment (does not install anything)")
    check.set_defaults(func=cmd_check_env)

    init = sub.add_parser("init", help="Create analysis workspace + starter notebook template")
    init.add_argument("--device-id", required=True)
    init.add_argument("--workdir", help="Workdir root (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    init.add_argument("--run-id", help="Run id (default: latest for device)")
    init.add_argument("--input", help="Path to decoded dataset (parquet/csv/json)")
    init.add_argument("--overwrite", action="store_true")
    init.add_argument(
        "--template",
        choices=["eda", "cleaning", "metrics", "anomaly", "viz", "full"],
        default="eda",
        help="Notebook template to generate",
    )
    init.set_defaults(func=cmd_init)

    launch = sub.add_parser("launch", help="Launch Jupyter in the analysis notebooks folder")
    launch.add_argument("--device-id", required=True)
    launch.add_argument("--workdir", help="Workdir root (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    launch.add_argument("--run-id", help="Run id (default: latest for device)")
    launch.add_argument("--mode", choices=["lab", "notebook"], default="lab")
    launch.add_argument("--port", type=int)
    launch.add_argument("--no-browser", action="store_true")
    launch.set_defaults(func=cmd_launch)

    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
