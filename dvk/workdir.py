#!/usr/bin/env python3
"""
DVK workdir utilities.

Goal: keep private device data / reports out of the code repository by default.

Default:
  DVK_WORKDIR = %USERPROFILE%\\DVK_Workspaces
  project_root = DVK_WORKDIR/Device-Verification-Kit

Override:
  - env: DVK_WORKDIR
  - CLI flags in scripts: --workdir / --run-id
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_SLUG = "Device-Verification-Kit"


def default_workdir_root() -> Path:
    return Path(os.environ.get("DVK_WORKDIR", str(Path.home() / "DVK_Workspaces"))).expanduser()


def project_workdir_root(workdir_root: Optional[Path] = None) -> Path:
    root = (workdir_root or default_workdir_root()).expanduser().resolve()
    return root / PROJECT_SLUG


def new_run_id(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now()
    return dt.strftime("%Y%m%d-%H%M%S")


def device_root(device_id: str, *, workdir_root: Optional[Path] = None) -> Path:
    return project_workdir_root(workdir_root) / device_id


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path
    raw_dir: Path
    processed_dir: Path
    reports_dir: Path
    logs_dir: Path


def run_paths(device_id: str, *, run_id: Optional[str] = None, workdir_root: Optional[Path] = None) -> RunPaths:
    did = str(device_id)
    rid = run_id or new_run_id()
    base = device_root(did, workdir_root=workdir_root) / "runs" / rid
    return RunPaths(
        run_id=rid,
        run_dir=base,
        raw_dir=base / "data" / "raw",
        processed_dir=base / "data" / "processed",
        reports_dir=base / "reports",
        logs_dir=base / "logs",
    )


def latest_run_id(device_id: str, *, workdir_root: Optional[Path] = None) -> Optional[str]:
    runs_dir = device_root(str(device_id), workdir_root=workdir_root) / "runs"
    if not runs_dir.exists():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.name)
    return candidates[-1].name

