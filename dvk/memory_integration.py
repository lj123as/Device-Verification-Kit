from __future__ import annotations

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


@dataclass(frozen=True)
class EmbeddedMemory:
    dvk_root: Path
    store_root: Path

    def _import_store(self):
        src = _embedded_memory_src(self.dvk_root)
        if not src.exists():
            raise FileNotFoundError(f"embedded-memory not found at {src}")
        sys.path.insert(0, str(src))
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
    src = _embedded_memory_src(dvk_root)
    if not src.exists():
        return None
    return EmbeddedMemory(dvk_root=dvk_root, store_root=device_root)
