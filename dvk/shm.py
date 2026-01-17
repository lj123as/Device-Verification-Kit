#!/usr/bin/env python3
"""
DVK shared-memory ring buffer for low-latency (near zero-copy) visualization.

Design goals:
- Fixed-capacity ring buffer: storage does not grow over time.
- Producer writes points; consumer reads latest window.
- Data stored as float32 columns for fast plotting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Tuple


try:
    import numpy as np  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: numpy\n"
        "Install: pip install numpy\n"
        f"Error: {e}"
    )


_CTRL_DTYPE = np.dtype(
    [
        ("version", "<u4"),
        ("capacity", "<u4"),
        ("write_index", "<u4"),
        ("_pad0", "<u4"),
        ("seq", "<u8"),
        ("last_write_ns", "<u8"),
    ]
)

_POINT_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("angle_deg", "<f4"),
        ("distance", "<f4"),
        ("intensity", "<f4"),
        ("frame_idx", "<u4"),
        ("point_idx", "<u4"),
    ]
)


@dataclass
class ShmHandles:
    ctrl_shm: shared_memory.SharedMemory
    data_shm: shared_memory.SharedMemory
    ctrl: "np.ndarray"
    data: "np.ndarray"
    owner: bool


def _names(base: str) -> Tuple[str, str]:
    return f"{base}.ctrl", f"{base}.data"


def create_ring(base_name: str, capacity_points: int) -> ShmHandles:
    if capacity_points <= 0:
        raise ValueError("capacity_points must be > 0")

    ctrl_name, data_name = _names(base_name)
    ctrl_shm = shared_memory.SharedMemory(name=ctrl_name, create=True, size=_CTRL_DTYPE.itemsize)
    data_shm = shared_memory.SharedMemory(name=data_name, create=True, size=_POINT_DTYPE.itemsize * capacity_points)

    ctrl = np.ndarray((1,), dtype=_CTRL_DTYPE, buffer=ctrl_shm.buf)
    data = np.ndarray((capacity_points,), dtype=_POINT_DTYPE, buffer=data_shm.buf)

    ctrl["version"][0] = 1
    ctrl["capacity"][0] = capacity_points
    ctrl["write_index"][0] = 0
    ctrl["seq"][0] = 0
    ctrl["last_write_ns"][0] = 0
    data.fill(0)

    return ShmHandles(ctrl_shm=ctrl_shm, data_shm=data_shm, ctrl=ctrl, data=data, owner=True)


def unlink_ring(base_name: str) -> None:
    """
    Best-effort unlink of an existing ring buffer by name.
    Safe to call even if it doesn't exist.
    """
    ctrl_name, data_name = _names(base_name)
    for name in (ctrl_name, data_name):
        try:
            shm = shared_memory.SharedMemory(name=name, create=False)
        except FileNotFoundError:
            continue
        try:
            shm.unlink()
        except Exception:
            pass
        try:
            shm.close()
        except Exception:
            pass


def create_or_attach(base_name: str, capacity_points: int, overwrite: bool = False) -> ShmHandles:
    if overwrite:
        unlink_ring(base_name)
    try:
        return create_ring(base_name, capacity_points=capacity_points)
    except FileExistsError:
        h = attach_ring(base_name)
        cap = int(h.ctrl["capacity"][0])
        if cap != int(capacity_points):
            raise ValueError(f"SharedMemory exists with capacity={cap}, requested capacity={capacity_points}")
        return h


def attach_ring(base_name: str) -> ShmHandles:
    ctrl_name, data_name = _names(base_name)
    ctrl_shm = shared_memory.SharedMemory(name=ctrl_name, create=False)
    ctrl = np.ndarray((1,), dtype=_CTRL_DTYPE, buffer=ctrl_shm.buf)
    cap = int(ctrl["capacity"][0])
    data_shm = shared_memory.SharedMemory(name=data_name, create=False)
    data = np.ndarray((cap,), dtype=_POINT_DTYPE, buffer=data_shm.buf)
    return ShmHandles(ctrl_shm=ctrl_shm, data_shm=data_shm, ctrl=ctrl, data=data, owner=False)


def close_ring(h: ShmHandles, unlink: bool = False) -> None:
    try:
        h.ctrl_shm.close()
    except Exception:
        pass
    try:
        h.data_shm.close()
    except Exception:
        pass
    if unlink and h.owner:
        try:
            h.ctrl_shm.unlink()
        except Exception:
            pass
        try:
            h.data_shm.unlink()
        except Exception:
            pass


def write_points(h: ShmHandles, rows: "np.ndarray") -> None:
    n = int(rows.shape[0])
    if n <= 0:
        return
    cap = int(h.ctrl["capacity"][0])
    w = int(h.ctrl["write_index"][0])

    if n >= cap:
        rows = rows[-cap:]
        n = cap
        w = 0

    end = w + n
    if end <= cap:
        h.data[w:end] = rows
    else:
        first = cap - w
        h.data[w:cap] = rows[:first]
        h.data[0 : (end - cap)] = rows[first:]

    h.ctrl["write_index"][0] = (w + n) % cap
    h.ctrl["seq"][0] = int(h.ctrl["seq"][0]) + 1
    h.ctrl["last_write_ns"][0] = time.time_ns()


def read_latest(h: ShmHandles, max_points: int) -> "np.ndarray":
    cap = int(h.ctrl["capacity"][0])
    if max_points <= 0:
        return h.data[:0].copy()
    max_points = min(int(max_points), cap)
    w = int(h.ctrl["write_index"][0])

    start = (w - max_points) % cap
    if start < w:
        return h.data[start:w].copy()
    return np.concatenate([h.data[start:cap], h.data[0:w]]).copy()

