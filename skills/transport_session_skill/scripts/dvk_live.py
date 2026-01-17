#!/usr/bin/env python3
"""
DVK live streaming helper.

Producer:
- Reads UART bytes
- Frames using protocol.json (header + length + checksum)
- Decodes bytes (minimal fields) and applies semantic transform via commands.yaml
- Publishes point rows into shared-memory ring buffer (fixed capacity)

Consumer (Jupyter/Streamlit):
- Attaches to shared memory and renders latest window.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


def find_dvk_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def load_protocol(protocol_path: Path) -> dict:
    try:
        return json.loads(protocol_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"protocol.json not found: {protocol_path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {protocol_path}: {e}")


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: PyYAML\n"
            "Install: pip install pyyaml\n"
            f"Error: {e}"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def extract_header(frame_spec: dict) -> bytes:
    header = frame_spec.get("header")
    if not isinstance(header, list) or not header:
        raise ValueError("frame.header must be a non-empty list")
    b = bytearray()
    for token in header:
        if not isinstance(token, str) or not token.lower().startswith("0x") or len(token) != 4:
            raise ValueError(f"Invalid header byte token: {token!r}")
        b.append(int(token, 16))
    return bytes(b)


def parse_uint(value_bytes: bytes, value_type: str) -> int:
    if value_type == "uint8":
        return value_bytes[0]
    if value_type == "uint16_le":
        return int.from_bytes(value_bytes, "little", signed=False)
    if value_type == "uint16_be":
        return int.from_bytes(value_bytes, "big", signed=False)
    if value_type == "uint32_le":
        return int.from_bytes(value_bytes, "little", signed=False)
    if value_type == "uint32_be":
        return int.from_bytes(value_bytes, "big", signed=False)
    raise ValueError(f"Unsupported length field type: {value_type}")


def resolve_index(index: int, total_len: int) -> int:
    return index if index >= 0 else total_len + index


class LengthSpec:
    def __init__(self, mode: str, *, value: Optional[int] = None, field: Optional[dict] = None, overhead_bytes: int = 0, unit_bytes: int = 0):
        self.mode = mode
        self.value = value
        self.field = field or {}
        self.overhead_bytes = int(overhead_bytes)
        self.unit_bytes = int(unit_bytes)

    @staticmethod
    def from_frame(frame_spec: dict) -> "LengthSpec":
        length = frame_spec.get("length")
        if not isinstance(length, dict):
            raise ValueError("frame.length must be an object")
        mode = str(length.get("mode"))
        if mode == "fixed":
            return LengthSpec(mode="fixed", value=int(length["value"]))
        if mode == "dynamic":
            field = length.get("field", {})
            return LengthSpec(mode="dynamic", field=field, overhead_bytes=int(length["overhead_bytes"]))
        if mode == "counted":
            field = length.get("count_field", {})
            return LengthSpec(
                mode="counted",
                field=field,
                unit_bytes=int(length["unit_bytes"]),
                overhead_bytes=int(length["overhead_bytes"]),
            )
        raise ValueError(f"Unsupported length.mode: {mode}")

    def total_length(self, prefix: bytes) -> int:
        if self.mode == "fixed":
            assert self.value is not None
            return int(self.value)
        off = int(self.field.get("offset", -1))
        ln = int(self.field.get("length", -1))
        tp = str(self.field.get("type", ""))
        if off < 0 or ln <= 0:
            return -1
        if len(prefix) < off + ln:
            return -1
        v = parse_uint(prefix[off : off + ln], tp)
        if self.mode == "dynamic":
            return int(v) + self.overhead_bytes
        # counted
        return int(v) * self.unit_bytes + self.overhead_bytes


def _decode_raw_fields(frame: bytes, frame_spec: dict) -> Dict[str, Any]:
    # Minimal decoder (mirrors protocol_decode_skill behavior for common scalar types + bytes)
    import struct

    def parse_value(data: bytes, value_type: str) -> Any:
        if value_type == "uint8":
            return data[0] if len(data) >= 1 else None
        if value_type == "uint16_le":
            return struct.unpack("<H", data[:2])[0] if len(data) >= 2 else None
        if value_type == "uint16_be":
            return struct.unpack(">H", data[:2])[0] if len(data) >= 2 else None
        if value_type == "uint32_le":
            return struct.unpack("<I", data[:4])[0] if len(data) >= 4 else None
        if value_type == "uint32_be":
            return struct.unpack(">I", data[:4])[0] if len(data) >= 4 else None
        if value_type == "bytes":
            return data.hex()
        return data.hex()

    def resolve_len(length_spec: Any, record: Dict[str, Any]) -> int:
        if isinstance(length_spec, int):
            return length_spec
        if isinstance(length_spec, dict):
            ref = length_spec.get("ref")
            mul = int(length_spec.get("mul", 1))
            add = int(length_spec.get("add", 0))
            if ref and ref in record:
                return int(record[ref]) * mul + add
        return 0

    rec: Dict[str, Any] = {}
    for field_def in frame_spec.get("fields", []):
        name = str(field_def["name"])
        offset = int(field_def["offset"])
        ln = resolve_len(field_def["length"], rec)
        if offset < 0:
            offset = len(frame) + offset
        if offset < 0 or offset + ln > len(frame):
            continue
        raw = frame[offset : offset + ln]
        rec[name] = parse_value(raw, str(field_def["type"]))
    return rec


def _iter_framed_bytes(read_chunk: callable, header: bytes, length_spec: LengthSpec, checksum_spec: Optional[dict]) -> Iterator[bytes]:
    from dvk.checksums import verify_checksum  # type: ignore

    buf = bytearray()
    while True:
        chunk = read_chunk()
        if not chunk:
            continue
        buf.extend(chunk)
        while True:
            idx = buf.find(header)
            if idx < 0:
                if len(buf) > len(header):
                    del buf[: -len(header)]
                break
            if idx > 0:
                del buf[:idx]
            total_len = length_spec.total_length(buf)
            if total_len < 0 or len(buf) < total_len:
                break
            frame = bytes(buf[:total_len])
            del buf[:total_len]
            if checksum_spec and isinstance(checksum_spec, dict):
                try:
                    if not verify_checksum(frame, checksum_spec):
                        continue
                except Exception:
                    continue
            yield frame


def _records_to_points_numpy(records: List[Dict[str, Any]]) -> "Any":
    import numpy as np  # type: ignore
    import math
    # expecting point rows with keys: x,y,angle_deg,distance_raw,intensity,_frame_idx,_point_idx
    dtype = np.dtype(
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
    out = np.zeros((len(records),), dtype=dtype)
    for i, r in enumerate(records):
        angle_deg = float(r.get("angle_deg", 0.0) or 0.0)
        distance = float(r.get("distance_raw", 0.0) or 0.0)

        x = r.get("x")
        y = r.get("y")
        # If x/y are missing, derive from polar coordinates (generic, not protocol-specific).
        if x is None or y is None:
            theta = math.radians(angle_deg)
            x = math.cos(theta) * distance
            y = math.sin(theta) * distance

        out["x"][i] = float(x or 0.0)
        out["y"][i] = float(y or 0.0)
        out["angle_deg"][i] = angle_deg
        out["distance"][i] = distance
        out["intensity"][i] = float(r.get("intensity", r.get("brightness", 0.0)) or 0.0)
        out["frame_idx"][i] = int(r.get("_frame_idx") or 0)
        out["point_idx"][i] = int(r.get("_point_idx") or 0)
    return out


def cmd_uart_publish(args: argparse.Namespace) -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        import serial  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: pyserial\n"
            "Install: pip install pyserial\n"
            f"Error: {e}"
        )

    dvk_root = find_dvk_root(Path(__file__).parent)
    sys.path.insert(0, str(dvk_root))
    from dvk.shm import create_or_attach, write_points, close_ring  # type: ignore
    from dvk.semantics import apply_semantics  # type: ignore

    # Accept either an explicit path or a protocol_id (resolved via DVK_SPEC_ROOT / workdir / repo demo).
    from dvk.assets import resolve_protocol  # type: ignore

    protocol_path = resolve_protocol(str(args.protocol))
    protocol = load_protocol(protocol_path)
    frames = protocol.get("frames", [])
    if not frames:
        raise SystemExit("protocol.json missing frames[]")

    frame_spec = frames[0]
    header = extract_header(frame_spec)
    length_spec = LengthSpec.from_frame(frame_spec)
    checksum_spec = frame_spec.get("checksum")

    commands_doc: Optional[dict] = None
    if args.commands:
        from dvk.assets import resolve_command_set  # type: ignore

        commands_path = resolve_command_set(str(args.commands))
        commands_doc = load_yaml(commands_path)

    shm_base = args.shm_name or f"dvk.{args.device_id}"
    ring = create_or_attach(shm_base, capacity_points=int(args.capacity_points), overwrite=args.overwrite_shm)
    print(f"SharedMemory: {shm_base} (capacity_points={args.capacity_points})")

    port = args.port
    baud = int(args.baudrate)
    window_s = float(args.window_s)
    fps = float(args.fps)
    sleep_s = 1.0 / fps if fps > 0 else 0.0

    frame_idx = 0
    last_emit = 0.0

    with serial.Serial(port=port, baudrate=baud, timeout=0.2) as ser:
        def read_chunk() -> bytes:
            return ser.read(4096)

        try:
            for frame in _iter_framed_bytes(read_chunk, header, length_spec, checksum_spec):
                raw = _decode_raw_fields(frame, frame_spec)
                raw["_frame_idx"] = frame_idx
                raw["_frame_name"] = frame_spec.get("name")
                frame_idx += 1

                if commands_doc:
                    sem = apply_semantics([raw], commands=commands_doc)
                    if sem.applied:
                        # Convert to x/y on the fly
                        import math
                        pts = []
                        for p in sem.records:
                            ang = float(p.get("angle_deg", 0.0))
                            dist = float(p.get("distance_raw", 0.0))
                            th = math.radians(ang)
                            p["x"] = dist * math.cos(th)
                            p["y"] = dist * math.sin(th)
                            pts.append(p)
                        rows = _records_to_points_numpy(pts)
                    else:
                        continue
                else:
                    continue

                now = time.time()
                # Throttle to target fps (device is 6Hz by default)
                if sleep_s > 0 and (now - last_emit) < sleep_s:
                    continue
                last_emit = now

                # Keep only the latest window by limiting to max points
                max_points = int(args.max_points)
                if max_points > 0 and len(rows) > max_points:
                    rows = rows[-max_points:]

                write_points(ring, rows)

                # Optional: periodic status
                if args.verbose and (frame_idx % 30 == 0):
                    try:
                        import numpy as np  # type: ignore

                        x = rows["x"].astype(float)
                        y = rows["y"].astype(float)
                        print(
                            "frames=%d last_points=%d window_s=%.2f seq=%d "
                            "x[min=%.2f max=%.2f std=%.2f] y[min=%.2f max=%.2f std=%.2f] x0%%=%.2f"
                            % (
                                frame_idx,
                                len(rows),
                                window_s,
                                int(ring.ctrl["seq"][0]),
                                float(np.min(x)),
                                float(np.max(x)),
                                float(np.std(x)),
                                float(np.min(y)),
                                float(np.max(y)),
                                float(np.std(y)),
                                float(np.mean(x == 0)) * 100.0,
                            )
                        )
                    except Exception:
                        print(f"frames={frame_idx} last_points={len(rows)} window_s={window_s} seq={int(ring.ctrl['seq'][0])}")
        finally:
            close_ring(ring, unlink=args.unlink)


def cmd_replay_csv(args: argparse.Namespace) -> None:
    """
    Replay an existing decoded.csv (semantic) as a live stream into shared memory.
    Useful when the COM port is busy or to validate the visualization pipeline.
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    dvk_root = find_dvk_root(Path(__file__).parent)
    sys.path.insert(0, str(dvk_root))

    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: pandas\n"
            "Install: pip install pandas\n"
            f"Error: {e}"
        )

    from dvk.shm import create_or_attach, write_points, close_ring  # type: ignore

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = dvk_root / input_path
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    df = pd.read_csv(input_path)
    required = {"_frame_idx", "_point_idx", "angle_deg", "distance_raw"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Input missing required columns: {sorted(missing)}")

    fps = float(args.fps)
    sleep_s = 1.0 / fps if fps > 0 else 0.0
    window_s = float(args.window_s)
    max_frames = int(max(1, round(window_s * fps)))
    max_points = int(args.max_points)

    shm_base = args.shm_name or f"dvk.{args.device_id}"
    ring = create_or_attach(shm_base, capacity_points=int(args.capacity_points), overwrite=args.overwrite_shm)
    print(f"SharedMemory: {shm_base} (capacity_points={args.capacity_points})")

    # Group by frame
    frames = [g for _, g in df.groupby("_frame_idx")]
    if not frames:
        raise SystemExit("No frames found in CSV")

    import math
    import numpy as np  # type: ignore

    def to_rows(frame_df) -> Any:
        theta = np.deg2rad(frame_df["angle_deg"].to_numpy(dtype=float))
        r = frame_df["distance_raw"].to_numpy(dtype=float)
        x = r * np.cos(theta)
        y = r * np.sin(theta)

        out = np.zeros((len(frame_df),), dtype=np.dtype(
            [
                ("x", "<f4"),
                ("y", "<f4"),
                ("angle_deg", "<f4"),
                ("distance", "<f4"),
                ("intensity", "<f4"),
                ("frame_idx", "<u4"),
                ("point_idx", "<u4"),
            ]
        ))
        out["x"] = x.astype("<f4")
        out["y"] = y.astype("<f4")
        out["angle_deg"] = frame_df["angle_deg"].to_numpy(dtype=float).astype("<f4")
        out["distance"] = r.astype("<f4")
        if "intensity" in frame_df.columns:
            out["intensity"] = frame_df["intensity"].to_numpy(dtype=float).astype("<f4")
        else:
            out["intensity"] = 0.0
        out["frame_idx"] = frame_df["_frame_idx"].to_numpy(dtype=int).astype("<u4")
        out["point_idx"] = frame_df["_point_idx"].to_numpy(dtype=int).astype("<u4")
        return out

    try:
        idx = 0
        while True:
            window = frames[max(0, idx - max_frames + 1) : idx + 1]
            rows = np.concatenate([to_rows(f) for f in window], axis=0)
            if max_points > 0 and len(rows) > max_points:
                rows = rows[-max_points:]
            write_points(ring, rows)
            idx = (idx + 1) % len(frames) if args.loop else (idx + 1)
            if not args.loop and idx >= len(frames):
                break
            if sleep_s > 0:
                time.sleep(sleep_s)
    finally:
        close_ring(ring, unlink=args.unlink)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_live.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("uart-publish", help="Capture UART -> frame -> semantic -> publish to shared memory ring")
    pub.add_argument("--device-id", required=True)
    pub.add_argument("--port", required=True, help="COMx")
    pub.add_argument("--baudrate", type=int, default=230400)
    pub.add_argument("--protocol", required=True, help="protocol.json path")
    pub.add_argument("--commands", help="commands.yaml path (enables semantic decode)")
    pub.add_argument("--shm-name", help="SharedMemory base name (default dvk.<device_id>)")
    pub.add_argument("--capacity-points", type=int, default=200000)
    pub.add_argument("--max-points", type=int, default=50000, help="Max points per publish")
    pub.add_argument("--window-s", type=float, default=5.0, help="Intended consumer window (seconds)")
    pub.add_argument("--fps", type=float, default=6.0)
    pub.add_argument("--unlink", action="store_true", help="Unlink shared memory on exit (owner only)")
    pub.add_argument("--overwrite-shm", action="store_true", help="Unlink existing ring and recreate")
    pub.add_argument("--verbose", action="store_true")
    pub.set_defaults(func=cmd_uart_publish)

    rep = sub.add_parser("replay-csv", help="Replay decoded.csv into shared memory (no device required)")
    rep.add_argument("--device-id", required=True)
    rep.add_argument("--input", required=True, help="Path to semantic decoded.csv (angle_deg + distance_raw + _frame_idx/_point_idx)")
    rep.add_argument("--shm-name", help="SharedMemory base name (default dvk.<device_id>)")
    rep.add_argument("--capacity-points", type=int, default=200000)
    rep.add_argument("--max-points", type=int, default=50000)
    rep.add_argument("--window-s", type=float, default=5.0)
    rep.add_argument("--fps", type=float, default=6.0)
    rep.add_argument("--loop", action="store_true")
    rep.add_argument("--unlink", action="store_true")
    rep.add_argument("--overwrite-shm", action="store_true")
    rep.set_defaults(func=cmd_replay_csv)

    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
