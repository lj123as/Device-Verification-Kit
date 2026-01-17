#!/usr/bin/env python3
"""
Resolve DVK protocol assets (protocol.json / commands.yaml / model yaml).

Isolation goal:
- Public/demo assets live under repo `spec/` (git-tracked examples only).
- Private assets live outside the repo by default:
    $DVK_SPEC_ROOT (preferred)
    or $DVK_WORKDIR/Device-Verification-Kit/_assets/spec

Callers may pass either:
- an explicit filesystem path, or
- an id (protocol_id / command_set_id / model_id)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dvk.workdir import default_workdir_root, project_workdir_root


def repo_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise RuntimeError("Cannot locate repo root (missing .claude-plugin/plugin.json)")


def default_spec_root() -> Path:
    env = os.environ.get("DVK_SPEC_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # Default private spec root under workdir
    return (project_workdir_root(default_workdir_root()) / "_assets" / "spec").resolve()


def _try_file(p: Path) -> Optional[Path]:
    try:
        if p.exists() and p.is_file():
            return p.resolve()
    except Exception:
        return None
    return None


def resolve_protocol(protocol: str, *, spec_root: Optional[Path] = None) -> Path:
    p = Path(protocol).expanduser()
    if p.is_absolute():
        hit = _try_file(p)
        if hit:
            return hit
        raise FileNotFoundError(str(p))
    # relative path (explicit)
    hit = _try_file(p)
    if hit:
        return hit

    root = (spec_root or default_spec_root()).expanduser().resolve()
    # treat as protocol_id
    cand = root / "protocols" / protocol / "protocol.json"
    hit = _try_file(cand)
    if hit:
        return hit

    # fallback to repo demo spec
    cand2 = repo_root() / "spec" / "protocols" / protocol / "protocol.json"
    hit = _try_file(cand2)
    if hit:
        return hit

    raise FileNotFoundError(f"protocol not found: {protocol}")


def resolve_command_set(commands: str, *, spec_root: Optional[Path] = None) -> Path:
    p = Path(commands).expanduser()
    if p.is_absolute():
        hit = _try_file(p)
        if hit:
            return hit
        raise FileNotFoundError(str(p))
    hit = _try_file(p)
    if hit:
        return hit

    root = (spec_root or default_spec_root()).expanduser().resolve()
    cand = root / "command_sets" / commands / "commands.yaml"
    hit = _try_file(cand)
    if hit:
        return hit

    cand2 = repo_root() / "spec" / "command_sets" / commands / "commands.yaml"
    hit = _try_file(cand2)
    if hit:
        return hit

    raise FileNotFoundError(f"command_set not found: {commands}")


def resolve_model(model: str, *, spec_root: Optional[Path] = None) -> Path:
    p = Path(model).expanduser()
    if p.is_absolute():
        hit = _try_file(p)
        if hit:
            return hit
        raise FileNotFoundError(str(p))
    hit = _try_file(p)
    if hit:
        return hit

    root = (spec_root or default_spec_root()).expanduser().resolve()
    cand = root / "models" / f"{model}.yaml"
    hit = _try_file(cand)
    if hit:
        return hit

    cand2 = repo_root() / "spec" / "models" / f"{model}.yaml"
    hit = _try_file(cand2)
    if hit:
        return hit

    raise FileNotFoundError(f"model not found: {model}")

