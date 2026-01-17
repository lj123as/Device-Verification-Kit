#!/usr/bin/env python3
"""
DVK checksum utilities shared across skills.

This module centralizes checksum algorithms so individual skills don't carry
protocol-specific checksum implementations.
"""

from __future__ import annotations

from typing import Any, Dict, List


def reflect_bits(value: int, width: int) -> int:
    result = 0
    for i in range(width):
        if value & (1 << i):
            result |= 1 << (width - 1 - i)
    return result


def crc_compute(data: bytes, width: int, poly: int, init: int, xorout: int, refin: bool, refout: bool) -> int:
    """
    Bitwise CRC with configurable parameters.
    NOTE: `poly` is used as-is. For reflected CRCs (refin=True) provide the reflected polynomial.
    """
    mask = (1 << width) - 1
    crc = init & mask

    if refin:
        for b in data:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ poly if (crc & 1) else (crc >> 1)
        crc &= mask
    else:
        topbit = 1 << (width - 1)
        for b in data:
            crc ^= (b << (width - 8)) & mask
            for _ in range(8):
                crc = ((crc << 1) ^ poly) & mask if (crc & topbit) else (crc << 1) & mask

    if refout:
        crc = reflect_bits(crc, width)
    crc ^= xorout
    return crc & mask


def checksum_sum8(frame: bytes, start: int, end: int) -> int:
    return sum(frame[start : end + 1]) & 0xFF


def checksum_cs15(data: bytes) -> int:
    """
    CS15 from 《激光雷达通信协议_V0.1》 pseudo-code:
    - group bytes into 16-bit little-endian ints
    - chk32 = (chk32 << 1) + data_int
    - checksum = (chk32 & 0x7FFF) + (chk32 >> 15)
    - checksum = checksum & 0x7FFF
    """
    if len(data) % 2 == 1:
        data = data + b"\x00"
    chk32 = 0
    for i in range(0, len(data), 2):
        data_int = data[i] | (data[i + 1] << 8)
        chk32 = (chk32 << 1) + data_int
    checksum = (chk32 & 0x7FFF) + (chk32 >> 15)
    return int(checksum) & 0x7FFF


def resolve_index(index: int, total_len: int) -> int:
    return index if index >= 0 else total_len + index


def _checksum_nbytes(store_format: str) -> int:
    if store_format == "uint8":
        return 1
    if store_format.startswith("uint16_"):
        return 2
    if store_format.startswith("uint32_"):
        return 4
    raise ValueError(f"Unsupported store_format: {store_format}")


def read_expected_checksum(frame: bytes, store_at: int, store_format: str) -> int:
    n = _checksum_nbytes(store_format)
    start = resolve_index(store_at, len(frame))
    end = start + n
    if start < 0 or end > len(frame):
        raise ValueError("Checksum field out of bounds")
    raw = frame[start:end]
    if store_format == "uint8":
        return raw[0]
    if store_format.endswith("_le"):
        return int.from_bytes(raw, "little", signed=False)
    if store_format.endswith("_be"):
        return int.from_bytes(raw, "big", signed=False)
    raise ValueError(f"Unsupported store_format: {store_format}")


def checksum_xor16_slices(frame: bytes, params: Dict[str, Any]) -> int:
    """
    Generic XOR16 checksum:
    - xor_low is XOR of frame[offset] for offsets in `seed_low_offsets`
    - xor_up  is XOR of frame[offset] for offsets in `seed_up_offsets`
    - then process one or more `data_slices`, each iterates positions with `stride`:
      - xor_low XOR= frame[pos + rel] for rel in `low_rel_offsets`
      - xor_up  XOR= frame[pos + rel] for rel in `up_rel_offsets`
    Returns (xor_up<<8) | xor_low.
    """
    seed_low_offsets: List[int] = list(params.get("seed_low_offsets", []))
    seed_up_offsets: List[int] = list(params.get("seed_up_offsets", []))
    data_slices: List[Dict[str, Any]] = list(params.get("data_slices", []))

    xor_low = 0
    xor_up = 0

    for off in seed_low_offsets:
        if 0 <= off < len(frame):
            xor_low ^= frame[off]
    for off in seed_up_offsets:
        if 0 <= off < len(frame):
            xor_up ^= frame[off]

    for sl in data_slices:
        start = int(sl.get("from", 0))
        end = int(sl.get("to", len(frame) - 1))
        stride = int(sl.get("stride", 1))
        low_rel = [int(x) for x in sl.get("low_rel_offsets", [])]
        up_rel = [int(x) for x in sl.get("up_rel_offsets", [])]

        if stride <= 0:
            continue
        if end < 0:
            end = len(frame) + end
        if start < 0:
            start = len(frame) + start
        if start < 0:
            start = 0
        if end >= len(frame):
            end = len(frame) - 1
        if start > end:
            continue

        pos = start
        while pos <= end:
            for rel in low_rel:
                idx = pos + rel
                if 0 <= idx < len(frame):
                    xor_low ^= frame[idx]
            for rel in up_rel:
                idx = pos + rel
                if 0 <= idx < len(frame):
                    xor_up ^= frame[idx]
            pos += stride

    return ((xor_up << 8) | xor_low) & 0xFFFF


def compute_checksum(frame: bytes, checksum_spec: Dict[str, Any]) -> int:
    ctype = str(checksum_spec["type"])

    if ctype == "xor16_slices":
        params = checksum_spec.get("params")
        if not isinstance(params, dict):
            raise ValueError("xor16_slices requires checksum.params")
        return checksum_xor16_slices(frame, params)

    rng = checksum_spec.get("range")
    if not isinstance(rng, dict):
        raise ValueError("Checksum requires checksum.range")
    start = resolve_index(int(rng["from"]), len(frame))
    end = resolve_index(int(rng["to"]), len(frame))
    if start < 0 or end < 0 or start >= len(frame) or end >= len(frame) or end < start:
        raise ValueError("Invalid checksum.range")
    data = frame[start : end + 1]

    if ctype == "sum8":
        return checksum_sum8(frame, start, end)
    if ctype == "cs15":
        return checksum_cs15(data)
    if ctype in ("crc16", "crc32"):
        store_format = checksum_spec.get("store_format")
        if not store_format:
            raise ValueError("CRC requires checksum.store_format")
        params = checksum_spec.get("params")
        if not isinstance(params, dict):
            raise ValueError("CRC requires checksum.params")
        width = 16 if ctype == "crc16" else 32
        return crc_compute(
            data,
            width=width,
            poly=int(params["poly"]),
            init=int(params["init"]),
            xorout=int(params["xorout"]),
            refin=bool(params["refin"]),
            refout=bool(params["refout"]),
        )

    raise ValueError(f"Unsupported checksum type: {ctype}")


def verify_checksum(frame: bytes, checksum_spec: Dict[str, Any]) -> bool:
    ctype = str(checksum_spec["type"])

    store_format = checksum_spec.get("store_format")
    if not store_format:
        if ctype == "sum8":
            store_format = "uint8"
        elif ctype in ("cs15", "xor16_slices"):
            store_format = "uint16_le"
        else:
            raise ValueError("checksum.store_format is required for this checksum type")

    expected = read_expected_checksum(frame, int(checksum_spec["store_at"]), str(store_format))
    actual = compute_checksum(frame, checksum_spec)
    return int(actual) == int(expected)

