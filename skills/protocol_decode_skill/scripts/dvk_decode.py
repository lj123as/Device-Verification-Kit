#!/usr/bin/env python3
"""
DVK ProtocolDecodeSkill script.

Decodes framed bytes into structured data (CSV/JSON/Parquet) using protocol.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional


def find_dvk_root(start: Path) -> Path:
    """Find DVK root by locating .claude-plugin/plugin.json marker file."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def load_yaml_optional(path: Path) -> Optional[dict]:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return None


def load_protocol(protocol_path: Path) -> dict:
    try:
        return json.loads(protocol_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"protocol.json not found: {protocol_path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {protocol_path}: {e}")


def parse_value(data: bytes, value_type: str) -> Any:
    """Parse bytes into typed value based on protocol field type."""
    if value_type == "uint8":
        return data[0] if len(data) >= 1 else None
    elif value_type == "int8":
        return struct.unpack("b", data[:1])[0] if len(data) >= 1 else None
    elif value_type == "uint16_le":
        return struct.unpack("<H", data[:2])[0] if len(data) >= 2 else None
    elif value_type == "uint16_be":
        return struct.unpack(">H", data[:2])[0] if len(data) >= 2 else None
    elif value_type == "int16_le":
        return struct.unpack("<h", data[:2])[0] if len(data) >= 2 else None
    elif value_type == "int16_be":
        return struct.unpack(">h", data[:2])[0] if len(data) >= 2 else None
    elif value_type == "uint32_le":
        return struct.unpack("<I", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "uint32_be":
        return struct.unpack(">I", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "int32_le":
        return struct.unpack("<i", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "int32_be":
        return struct.unpack(">i", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "float32_le":
        return struct.unpack("<f", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "float32_be":
        return struct.unpack(">f", data[:4])[0] if len(data) >= 4 else None
    elif value_type == "bytes":
        return data.hex()
    else:
        return data.hex()


def resolve_field_length(length_spec: Any, record: Dict[str, Any], frame_len: int) -> int:
    """Resolve field length which can be int or {"ref": "field_name", "add": N}."""
    if isinstance(length_spec, int):
        return length_spec
    if isinstance(length_spec, dict):
        ref_field = length_spec.get("ref")
        mul_val = length_spec.get("mul", 1)
        add_val = length_spec.get("add", 0)
        if ref_field and ref_field in record:
            base = int(record[ref_field])
            try:
                mul_val = int(mul_val)
            except Exception:
                mul_val = 1
            return (base * mul_val) + int(add_val)
    return 0


@dataclass
class DecodeStats:
    total_frames: int = 0
    decoded_ok: int = 0
    decode_errors: int = 0
    field_names: List[str] = field(default_factory=list)


def decode_frame(frame: bytes, frame_spec: dict, record: Dict[str, Any]) -> bool:
    """Decode a single frame according to frame_spec, populating record dict."""
    fields = frame_spec.get("fields", [])

    for field_def in fields:
        name = field_def["name"]
        offset = int(field_def["offset"])
        length = resolve_field_length(field_def["length"], record, len(frame))
        ftype = field_def["type"]

        if offset < 0:
            offset = len(frame) + offset
        if offset < 0 or offset + length > len(frame):
            return False

        raw = frame[offset:offset + length]
        value = parse_value(raw, ftype)
        record[name] = value

    return True


def extract_header(frame_spec: dict) -> bytes:
    header = frame_spec.get("header", [])
    if not isinstance(header, list) or not header:
        raise ValueError("frame.header must be a non-empty list")
    header_bytes = bytearray()
    for token in header:
        if isinstance(token, str) and token.lower().startswith("0x"):
            header_bytes.append(int(token, 16))
    return bytes(header_bytes)


def get_frame_length(frame_spec: dict, data: bytes) -> int:
    """Determine frame length from length spec."""
    length_spec = frame_spec.get("length", {})
    mode = length_spec.get("mode", "fixed")

    if mode == "fixed":
        return length_spec.get("value", 0)
    elif mode == "dynamic":
        field_def = length_spec.get("field", {})
        offset = field_def.get("offset", 0)
        flen = field_def.get("length", 1)
        ftype = field_def.get("type", "uint8")
        overhead = length_spec.get("overhead_bytes", 0)

        if len(data) < offset + flen:
            return -1

        raw = data[offset:offset + flen]
        payload_len = parse_value(raw, ftype)
        if payload_len is None:
            return -1
        return payload_len + overhead
    elif mode == "counted":
        field_def = length_spec.get("count_field", {})
        offset = field_def.get("offset", 0)
        flen = field_def.get("length", 1)
        ftype = field_def.get("type", "uint8")
        overhead = length_spec.get("overhead_bytes", 0)
        unit_bytes = length_spec.get("unit_bytes", 0)
        if len(data) < offset + flen:
            return -1
        raw = data[offset:offset + flen]
        count = parse_value(raw, ftype)
        if count is None:
            return -1
        return int(overhead) + (int(count) * int(unit_bytes))

    return -1


def decode_frames_file(
    frames_path: Path,
    frame_spec: dict,
    add_frame_index: bool = True,
    add_timestamp: bool = False
) -> tuple[List[Dict[str, Any]], DecodeStats]:
    """Decode all frames from a binary file."""
    records = []
    stats = DecodeStats()

    header = extract_header(frame_spec)
    field_names = [f["name"] for f in frame_spec.get("fields", [])]
    if add_frame_index:
        field_names = ["_frame_idx"] + field_names
    if add_timestamp:
        field_names = ["_timestamp"] + field_names
    stats.field_names = field_names

    data = frames_path.read_bytes()
    pos = 0
    frame_idx = 0

    while pos < len(data):
        # Find header
        idx = data.find(header, pos)
        if idx < 0:
            break

        # Get frame length
        frame_len = get_frame_length(frame_spec, data[idx:])
        if frame_len <= 0 or idx + frame_len > len(data):
            pos = idx + 1
            continue

        frame = data[idx:idx + frame_len]
        stats.total_frames += 1

        record: Dict[str, Any] = {}
        if add_timestamp:
            record["_timestamp"] = None  # No timestamp source in offline mode
        if add_frame_index:
            record["_frame_idx"] = frame_idx

        if decode_frame(frame, frame_spec, record):
            records.append(record)
            stats.decoded_ok += 1
        else:
            stats.decode_errors += 1

        frame_idx += 1
        pos = idx + frame_len

    return records, stats


def write_csv(records: List[Dict[str, Any]], output_path: Path, field_names: List[str]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_names, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row: Dict[str, Any] = {}
            for k in field_names:
                v = r.get(k)
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
            writer.writerow(row)


def write_json(records: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def write_parquet(records: List[Dict[str, Any]], output_path: Path) -> None:
    try:
        import pandas as pd
        df = pd.DataFrame(records)
        df.to_parquet(output_path, index=False)
    except ImportError:
        raise SystemExit("pandas/pyarrow not installed. Install with: pip install pandas pyarrow")


def cmd_decode(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    # Workdir (private outputs) — defaults to %USERPROFILE%/DVK_Workspaces
    import sys as _sys
    _sys.path.insert(0, str(dvk_root))
    from dvk.workdir import default_workdir_root, latest_run_id, run_paths  # type: ignore

    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()

    # Resolve protocol path
    if not args.protocol:
        raise SystemExit("Missing --protocol (expected: spec/protocols/<protocol_id>/protocol.json)")
    from dvk.assets import resolve_protocol  # type: ignore

    protocol_path = resolve_protocol(str(args.protocol))
    protocol = load_protocol(protocol_path)

    # Get frame spec
    frames = protocol.get("frames", [])
    if not frames:
        raise SystemExit("protocol.json missing frames[]")

    frame_spec = None
    if args.frame_name:
        frame_spec = next((f for f in frames if f.get("name") == args.frame_name), None)
        if frame_spec is None:
            raise SystemExit(f"Frame not found: {args.frame_name}")

    # Resolve input path
    if args.input:
        frames_path = Path(args.input)
        effective_run_id: Optional[str] = args.run_id
    else:
        effective_run_id = args.run_id or latest_run_id(device_id, workdir_root=workdir_root)
        if effective_run_id:
            frames_path = run_paths(device_id, run_id=effective_run_id, workdir_root=workdir_root).raw_dir / "frames.bin"
        else:
            frames_path = dvk_root / "data" / "raw" / device_id / "frames.bin"

    if not frames_path.exists():
        raise SystemExit(f"Frames file not found: {frames_path}")

    if frame_spec is None and args.auto_frame_by_if:
        selector = protocol.get("frame_selector")
        if isinstance(selector, dict) and selector.get("type") == "if_bits_v1":
            sample = frames_path.read_bytes()[:65535]
            # Expect IF at offset selector.if_offset relative to frame start.
            if_offset = int(selector.get("if_offset", 2))
            if len(sample) > if_offset:
                if_byte = sample[if_offset]
                b_bright = int(selector.get("brightness_bit", 0))
                b_speed = int(selector.get("speed_bit", 1))
                b_blen = int(selector.get("brightness_len_bit", 2))
                inv_bright = bool(selector.get("invert_brightness_bit", False))
                inv_speed = bool(selector.get("invert_speed_bit", False))
                inv_blen = bool(selector.get("invert_brightness_len_bit", False))
                has_bright = bool((if_byte >> b_bright) & 1) ^ inv_bright
                has_speed = bool((if_byte >> b_speed) & 1) ^ inv_speed
                bright_u16 = bool((if_byte >> b_blen) & 1) ^ inv_blen
                frames_map = selector.get("frames", {}) if isinstance(selector.get("frames", {}), dict) else {}
                key = None
                if not has_speed and not has_bright:
                    key = "no_speed_dist_only"
                elif has_speed and not has_bright:
                    key = "speed_dist_only"
                elif (not has_speed) and has_bright and (not bright_u16):
                    key = "no_speed_dist_brightness_u8"
                elif has_speed and has_bright and (not bright_u16):
                    key = "speed_dist_brightness_u8"
                elif (not has_speed) and has_bright and bright_u16:
                    key = "no_speed_dist_brightness_u16"
                elif has_speed and has_bright and bright_u16:
                    key = "speed_dist_brightness_u16"
                if key and isinstance(frames_map.get(key), str):
                    frame_name = frames_map[key]
                    frame_spec = next((f for f in frames if f.get("name") == frame_name), None)

    if frame_spec is None:
        frame_spec = frames[0]

    # Decode
    records, stats = decode_frames_file(
        frames_path,
        frame_spec,
        add_frame_index=not args.no_index,
        add_timestamp=args.add_timestamp
    )

    # Attach frame name for semantic transforms
    for r in records:
        r.setdefault("_frame_name", frame_spec.get("name"))

    # Semantic decode (optional; driven by commands.yaml telemetry section)
    semantic_records: List[Dict[str, Any]] = records
    semantic_applied = False
    semantic_reason = "semantic disabled"
    commands_path: Optional[Path] = None
    if args.commands:
        commands_path = Path(args.commands)
        if not commands_path.is_absolute():
            commands_path = dvk_root / commands_path
        cmd_doc = load_yaml_optional(commands_path)
        if cmd_doc is None:
            semantic_reason = f"commands.yaml not loaded: {commands_path}"
        else:
            try:
                import sys
                sys.path.insert(0, str(dvk_root))
                from dvk.semantics import apply_semantics  # type: ignore

                res = apply_semantics(records, commands=cmd_doc)
                semantic_records = res.records
                semantic_applied = res.applied
                semantic_reason = res.reason
            except Exception as e:
                semantic_records = records
                semantic_applied = False
                semantic_reason = f"semantic failed: {e}"

    # Output directory (private by default)
    run = run_paths(device_id, run_id=effective_run_id, workdir_root=workdir_root)
    out_dir = run.processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write output based on format
    fmt = args.format.lower()
    def ext() -> str:
        return "csv" if fmt == "csv" else ("json" if fmt == "json" else "parquet")

    raw_out_path = out_dir / f"decoded_raw.{ext()}"
    semantic_out_path = out_dir / f"decoded.{ext()}"

    if fmt == "csv":
        # field names for semantic may differ from raw
        write_csv(records, raw_out_path, stats.field_names)
        semantic_fields = sorted({k for r in semantic_records for k in r.keys()})
        write_csv(semantic_records, semantic_out_path, semantic_fields)
    elif fmt == "json":
        write_json(records, raw_out_path)
        write_json(semantic_records, semantic_out_path)
    elif fmt == "parquet":
        write_parquet(records, raw_out_path)
        write_parquet(semantic_records, semantic_out_path)
    else:
        raise SystemExit(f"Unsupported format: {fmt}")

    # Write metadata
    meta = {
        "device_id": device_id,
        "run_id": run.run_id,
        "workdir": str(workdir_root),
        "protocol": str(protocol_path),
        "frame_name": frame_spec.get("name"),
        "input": str(frames_path),
        "outputs": {
            "raw": str(raw_out_path),
            "semantic": str(semantic_out_path),
        },
        "commands": str(commands_path) if commands_path else None,
        "semantic": {
            "applied": semantic_applied,
            "reason": semantic_reason,
        },
        "format": fmt,
        "stats": {
            "total_frames": stats.total_frames,
            "decoded_ok": stats.decoded_ok,
            "decode_errors": stats.decode_errors,
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    meta_path = out_dir / "decode_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(meta["stats"], ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_decode.py", description="Decode framed bytes to structured data")
    p.add_argument("--device-id", required=True, help="Device ID (folder name)")
    p.add_argument("--workdir", help="Workdir root for outputs (default: ~/DVK_Workspaces or env DVK_WORKDIR)")
    p.add_argument("--run-id", help="Run id (default: latest for device, else auto timestamp)")
    p.add_argument("--input", help="Path to frames.bin (default: workdir latest run frames.bin)")
    p.add_argument("--protocol", required=True, help="Path to protocol.json (e.g., spec/protocols/<protocol_id>/protocol.json)")
    p.add_argument("--commands", help="Path to commands.yaml (optional; enables semantic decode via telemetry section)")
    p.add_argument("--frame-name", help="Frame name to decode (default: first frame)")
    p.add_argument("--auto-frame-by-if", action="store_true", help="Auto-select frame by IF bits (requires protocol.frame_selector)")
    p.add_argument("--format", choices=["csv", "json", "parquet"], default="csv", help="Output format")
    p.add_argument("--no-index", action="store_true", help="Do not add _frame_idx column")
    p.add_argument("--add-timestamp", action="store_true", help="Add _timestamp column (offline: null)")
    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    cmd_decode(args)


if __name__ == "__main__":
    main()
