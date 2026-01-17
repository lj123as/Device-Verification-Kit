#!/usr/bin/env python3
"""
DVK semantic decoding utilities shared across skills.

Semantic decoding turns byte-level decoded records into analysis-ready tables
based on rules defined in commands.yaml (CommandSet + TelemetrySet).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SemanticResult:
    records: List[Dict[str, Any]]
    applied: bool
    reason: str


def _hex_to_bytes(value: Any) -> Optional[bytes]:
    if not isinstance(value, str):
        return None
    try:
        return bytes.fromhex(value)
    except Exception:
        return None


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _angle_deg_from_raw(raw: int, right_shift: int, scale_div: float, offset: float) -> float:
    return ((raw >> right_shift) / scale_div) + offset


def _wrap_delta(start_deg: float, end_deg: float, n: int) -> float:
    if n <= 1:
        return 0.0
    if end_deg < start_deg:
        return (end_deg + 360.0 - start_deg) / (n - 1)
    return (end_deg - start_deg) / (n - 1)


def _transform_triplet_pointcloud_v1(raw_records: List[Dict[str, Any]], cfg: Dict[str, Any]) -> SemanticResult:
    frame_name = cfg.get("frame_name")
    input_field = str(cfg.get("input_field") or "samples")
    count_ref = str(cfg.get("count_ref") or "lsn")

    out_records: List[Dict[str, Any]] = []

    dist_cfg = cfg.get("distance") or {}
    inten_cfg = cfg.get("intensity") or {}
    hr_cfg = cfg.get("hr_flag") or {}

    dist_b2_shift = int(dist_cfg.get("b2_shift", 6))
    dist_b1_shift = int(dist_cfg.get("b1_shift", 2))
    dist_b1_mask = int(dist_cfg.get("b1_mask", 0x3F))
    dist_mask = int(dist_cfg.get("mask", 0x3FFF))

    inten_b1_mask = int(inten_cfg.get("b1_mask", 0x03))
    inten_b1_shift = int(inten_cfg.get("b1_shift", 6))
    inten_b0_shift = int(inten_cfg.get("b0_shift", 2))
    inten_b0_mask = int(inten_cfg.get("b0_mask", 0x3F))

    hr_mask = int(hr_cfg.get("mask", 0x01))

    angle_cfg = cfg.get("angle") or {}
    start_field = str(angle_cfg.get("start_field") or "fsa")
    end_field = str(angle_cfg.get("end_field") or "lsa")
    right_shift = int(angle_cfg.get("right_shift", 1))
    scale_div = float(angle_cfg.get("scale_div", 64.0))
    offset = float(angle_cfg.get("offset", 0.0))

    include_frame_fields = list(cfg.get("include_frame_fields") or [])
    include_frame_fields = [str(x) for x in include_frame_fields if isinstance(x, (str, int, float))]

    for frame in raw_records:
        if frame_name and frame.get("_frame_name") != frame_name:
            continue

        payload = _hex_to_bytes(frame.get(input_field))
        count = _as_int(frame.get(count_ref)) or 0
        if payload is None or count <= 0:
            continue

        start_raw = _as_int(frame.get(start_field))
        end_raw = _as_int(frame.get(end_field))
        if start_raw is None or end_raw is None:
            continue

        start_deg = _angle_deg_from_raw(start_raw, right_shift=right_shift, scale_div=scale_div, offset=offset)
        end_deg = _angle_deg_from_raw(end_raw, right_shift=right_shift, scale_div=scale_div, offset=offset)
        delta = _wrap_delta(start_deg, end_deg, count)

        for i in range(count):
            base = i * 3
            if base + 2 >= len(payload):
                break
            b0 = payload[base]
            b1 = payload[base + 1]
            b2 = payload[base + 2]

            dist = ((b2 & 0xFF) << dist_b2_shift) | ((b1 >> dist_b1_shift) & dist_b1_mask)
            dist &= dist_mask

            inten = ((b1 & inten_b1_mask) << inten_b1_shift) | ((b0 >> inten_b0_shift) & inten_b0_mask)

            hr = b0 & hr_mask

            angle = start_deg + (i * delta)
            if angle >= 360.0:
                angle -= 360.0

            row: Dict[str, Any] = {
                "_frame_idx": frame.get("_frame_idx"),
                "_point_idx": i,
                "angle_deg": angle,
                "distance_raw": dist,
                "intensity": inten,
                "hr_flag": hr,
            }
            for k in include_frame_fields:
                row[k] = frame.get(k)
            out_records.append(row)

    if not out_records:
        return SemanticResult(records=[], applied=False, reason="No points produced (missing fields or empty payload).")
    return SemanticResult(records=out_records, applied=True, reason="triplet_pointcloud_v1 applied.")


def _transform_if_dn_pointcloud_v1(raw_records: List[Dict[str, Any]], cfg: Dict[str, Any]) -> SemanticResult:
    frame_name = cfg.get("frame_name")
    input_field = str(cfg.get("input_field") or "samples")
    count_ref = str(cfg.get("count_ref") or "dn")
    brightness_mode = str(cfg.get("brightness_mode") or "none")
    if brightness_mode not in ("none", "u8", "u16_le"):
        return SemanticResult(records=[], applied=False, reason=f"Invalid brightness_mode: {brightness_mode}")

    angle_cfg = cfg.get("angle") or {}
    start_field = str(angle_cfg.get("start_field") or "fa")
    end_field = str(angle_cfg.get("end_field") or "la")
    subtract_a000 = bool(angle_cfg.get("subtract_a000", True))
    scale_div = float(angle_cfg.get("scale_div", 64.0))
    offset = float(angle_cfg.get("offset", 0.0))

    speed_cfg = cfg.get("speed") or {}
    speed_field = str(speed_cfg.get("field") or "sp")
    speed_div = float(speed_cfg.get("div", 60.0 * 64.0))

    dist_cfg = cfg.get("distance") or {}
    dist_mask = int(dist_cfg.get("mask", 0x3FFF))

    include_frame_fields = list(cfg.get("include_frame_fields") or [])
    include_frame_fields = [str(x) for x in include_frame_fields if isinstance(x, (str, int, float))]

    if brightness_mode == "none":
        unit_bytes = 2
    elif brightness_mode == "u8":
        unit_bytes = 3
    else:
        unit_bytes = 4

    out_records: List[Dict[str, Any]] = []

    for frame in raw_records:
        if frame_name and frame.get("_frame_name") != frame_name:
            continue

        payload = _hex_to_bytes(frame.get(input_field))
        count = _as_int(frame.get(count_ref)) or 0
        if payload is None or count <= 0:
            continue

        start_raw = _as_int(frame.get(start_field))
        end_raw = _as_int(frame.get(end_field))
        if start_raw is None or end_raw is None:
            continue

        if subtract_a000:
            start_deg = ((start_raw - 0xA000) / scale_div) + offset
            end_deg = ((end_raw - 0xA000) / scale_div) + offset
        else:
            start_deg = (start_raw / scale_div) + offset
            end_deg = (end_raw / scale_div) + offset

        delta = _wrap_delta(start_deg, end_deg, count)

        speed_raw = _as_int(frame.get(speed_field))
        speed_rps = (float(speed_raw) / speed_div) if speed_raw is not None else None

        for i in range(count):
            base = i * unit_bytes
            if base + 1 >= len(payload):
                break
            dist = int.from_bytes(payload[base : base + 2], "little", signed=False) & dist_mask

            brightness = None
            if brightness_mode == "u8":
                if base + 2 >= len(payload):
                    break
                brightness = payload[base + 2]
            elif brightness_mode == "u16_le":
                if base + 3 >= len(payload):
                    break
                brightness = int.from_bytes(payload[base + 2 : base + 4], "little", signed=False)

            angle = start_deg + (i * delta)
            if angle >= 360.0:
                angle -= 360.0

            row: Dict[str, Any] = {
                "_frame_idx": frame.get("_frame_idx"),
                "_point_idx": i,
                "angle_deg": angle,
                "distance_raw": dist,
                "brightness": brightness,
                "speed_rps": speed_rps,
            }
            for k in include_frame_fields:
                row[k] = frame.get(k)
            out_records.append(row)

    if not out_records:
        return SemanticResult(records=[], applied=False, reason="No points produced (missing fields or empty payload).")
    return SemanticResult(records=out_records, applied=True, reason="if_dn_pointcloud_v1 applied.")


def apply_semantics(raw_records: List[Dict[str, Any]], *, commands: Dict[str, Any]) -> SemanticResult:
    telemetry = commands.get("telemetry")
    if not isinstance(telemetry, dict):
        return SemanticResult(records=raw_records, applied=False, reason="No telemetry section in commands.")

    transforms = telemetry.get("transforms")
    if not isinstance(transforms, list) or not transforms:
        return SemanticResult(records=raw_records, applied=False, reason="No telemetry.transforms rules.")

    t0 = transforms[0]
    if not isinstance(t0, dict) or "type" not in t0:
        return SemanticResult(records=raw_records, applied=False, reason="Invalid telemetry.transforms[0]")

    ttype = str(t0["type"])
    if ttype == "triplet_pointcloud_v1":
        return _transform_triplet_pointcloud_v1(raw_records, t0)
    if ttype == "if_dn_pointcloud_v1":
        return _transform_if_dn_pointcloud_v1(raw_records, t0)

    return SemanticResult(records=raw_records, applied=False, reason=f"Unsupported telemetry transform type: {ttype}")


def json_safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

