from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _is_truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def enabled() -> bool:
    return _is_truthy_env("DVK_EMBEDDED_MEMORY")


def _embedded_memory_src(dvk_root: Path) -> Path:
    return dvk_root / "tools" / "embedded-memory" / "src"

def _find_git_root(start: Path) -> Optional[Path]:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        git_path = parent / ".git"
        if git_path.is_dir() or git_path.is_file():
            return parent
    return None


def _store_mode() -> str:
    return os.environ.get("DVK_EMBEDDED_MEMORY_STORE_MODE", "repo").strip().lower()


def _store_root(*, device_root: Path) -> Path:
    override = os.environ.get("DVK_EMBEDDED_MEMORY_STORE", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    mode = _store_mode()
    if mode == "workdir":
        return device_root.resolve()

    # Default: repo mode (prefer the git root containing the device_root)
    return (_find_git_root(device_root) or device_root).resolve()


def available(*, dvk_root: Path) -> bool:
    if importlib.util.find_spec("embedded_memory") is not None:
        return True
    return _embedded_memory_src(dvk_root).exists()


@dataclass(frozen=True)
class EmbeddedMemory:
    dvk_root: Path
    store_root: Path

    def _import_store(self):
        # Prefer pip-installed package, fallback to local submodule src.
        try:
            from embedded_memory.store import MemoryStore  # type: ignore

            return MemoryStore
        except (ModuleNotFoundError, ImportError):
            pass

        src = _embedded_memory_src(self.dvk_root)
        if not src.exists():
            raise FileNotFoundError(
                "embedded-memory not available (install the package, or init submodule at tools/embedded-memory)"
            )
        src_s = str(src)
        if src_s not in sys.path:
            sys.path.insert(0, src_s)
        from embedded_memory.store import MemoryStore  # type: ignore

        return MemoryStore

    def observe(
        self,
        *,
        run_id: str,
        model_id: str,
        fw_version: str,
        source: str,
        content: str,
        instance_id: Optional[str] = None,
    ) -> None:
        MemoryStore = self._import_store()
        store = MemoryStore.from_root(str(self.store_root))
        store.observe(
            run_id=run_id,
            model_id=model_id,
            fw_version=fw_version,
            instance_id=instance_id,
            source=source,
            content=content,
        )

    def compile_prepare(self, *, run_id: str, out_path: Path, limit: int = 200) -> None:
        MemoryStore = self._import_store()
        store = MemoryStore.from_root(str(self.store_root))
        store.compile_prepare(run_id=run_id, out_path=out_path, limit=limit)

    def compile_apply(self, *, input_path: Path, request_path: Optional[Path] = None) -> None:
        MemoryStore = self._import_store()
        store = MemoryStore.from_root(str(self.store_root))
        store.compile_apply(input_path=input_path, request_path=request_path)

    def resolve(self, *, model_id: str, fw_version: str, instance_id: Optional[str] = None) -> dict:
        MemoryStore = self._import_store()
        store = MemoryStore.from_root(str(self.store_root))
        return store.resolve(model_id=model_id, fw_version=fw_version, instance_id=instance_id)


def for_device(
    *,
    dvk_root: Path,
    device_root: Path,
) -> Optional[EmbeddedMemory]:
    if not enabled():
        return None
    if not available(dvk_root=dvk_root):
        return None
    return EmbeddedMemory(dvk_root=dvk_root, store_root=_store_root(device_root=device_root))
