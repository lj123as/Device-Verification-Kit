#!/usr/bin/env python3
"""
DVK ProtocolEncodeSkill script.

Encodes business commands into protocol frames using commands.yaml and protocol.json.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def find_dvk_root(start: Path) -> Path:
    """Find DVK root by locating .claude-plugin/plugin.json marker file."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def load_commands(commands_path: Path) -> dict:
    try:
        return yaml.safe_load(commands_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"commands.yaml not found: {commands_path}")
    except yaml.YAMLError as e:
        raise SystemExit(f"Invalid YAML in {commands_path}: {e}")


def load_protocol(protocol_path: Path) -> dict:
    try:
        return json.loads(protocol_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"protocol.json not found: {protocol_path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {protocol_path}: {e}")


def encode_value(value: Any, value_type: str) -> bytes:
    """Encode a value to bytes based on type."""
    if value_type == "uint8":
        return struct.pack("B", int(value) & 0xFF)
    elif value_type == "int8":
        return struct.pack("b", int(value))
    elif value_type == "uint16_le":
        return struct.pack("<H", int(value) & 0xFFFF)
    elif value_type == "uint16_be":
        return struct.pack(">H", int(value) & 0xFFFF)
    elif value_type == "int16_le":
        return struct.pack("<h", int(value))
    elif value_type == "int16_be":
        return struct.pack(">h", int(value))
    elif value_type == "uint32_le":
        return struct.pack("<I", int(value) & 0xFFFFFFFF)
    elif value_type == "uint32_be":
        return struct.pack(">I", int(value) & 0xFFFFFFFF)
    elif value_type == "int32_le":
        return struct.pack("<i", int(value))
    elif value_type == "int32_be":
        return struct.pack(">i", int(value))
    elif value_type == "float32_le":
        return struct.pack("<f", float(value))
    elif value_type == "float32_be":
        return struct.pack(">f", float(value))
    elif value_type == "bytes":
        if isinstance(value, str):
            return bytes.fromhex(value)
        return bytes(value)
    else:
        raise ValueError(f"Unsupported type: {value_type}")


def find_command(commands_data: dict, selector: str) -> Optional[dict]:
    """Find command by name or hex ID."""
    commands = commands_data.get("commands", [])
    for cmd in commands:
        if cmd.get("name") == selector:
            return cmd
        cmd_id = cmd.get("id")
        if isinstance(cmd_id, int) and selector.lower().startswith("0x"):
            if cmd_id == int(selector, 16):
                return cmd
        elif str(cmd_id) == selector:
            return cmd
    return None


def build_payload(command: dict, params: Dict[str, Any]) -> bytes:
    """Build payload bytes from command definition and user params."""
    payload_def = command.get("payload", [])
    result = bytearray()

    for field in payload_def:
        name = field["name"]
        ftype = field.get("type", "uint8")

        if name not in params:
            raise ValueError(f"Missing required param: {name}")

        value = params[name]
        result.extend(encode_value(value, ftype))

    return bytes(result)


def checksum_sum8(data: bytes, start: int, end: int) -> int:
    return sum(data[start:end + 1]) & 0xFF


def reflect_bits(value: int, width: int) -> int:
    result = 0
    for i in range(width):
        if value & (1 << i):
            result |= 1 << (width - 1 - i)
    return result


def crc_compute(data: bytes, width: int, poly: int, init: int, xorout: int, refin: bool, refout: bool) -> int:
    mask = (1 << width) - 1
    crc = init & mask

    if refin:
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
        crc &= mask
    else:
        topbit = 1 << (width - 1)
        for b in data:
            crc ^= (b << (width - 8)) & mask
            for _ in range(8):
                if crc & topbit:
                    crc = ((crc << 1) ^ poly) & mask
                else:
                    crc = (crc << 1) & mask

    if refout:
        crc = reflect_bits(crc, width)
    crc ^= xorout
    return crc & mask


def encode_checksum(checksum_val: int, store_format: str) -> bytes:
    if store_format == "uint8":
        return struct.pack("B", checksum_val & 0xFF)
    elif store_format == "uint16_le":
        return struct.pack("<H", checksum_val & 0xFFFF)
    elif store_format == "uint16_be":
        return struct.pack(">H", checksum_val & 0xFFFF)
    elif store_format == "uint32_le":
        return struct.pack("<I", checksum_val & 0xFFFFFFFF)
    elif store_format == "uint32_be":
        return struct.pack(">I", checksum_val & 0xFFFFFFFF)
    else:
        raise ValueError(f"Unsupported store_format: {store_format}")


def build_frame(
    header: List[str],
    msg_id: int,
    payload: bytes,
    frame_spec: dict
) -> bytes:
    """Build a complete frame with header, length, msg_id, payload, and checksum."""
    # Header bytes
    header_bytes = bytearray()
    for token in header:
        if isinstance(token, str) and token.lower().startswith("0x"):
            header_bytes.append(int(token, 16))

    # Calculate frame structure based on typical pattern:
    # [header][length][msg_id][payload][checksum]
    length_spec = frame_spec.get("length", {})
    checksum_spec = frame_spec.get("checksum")

    # Build frame without checksum first
    frame = bytearray(header_bytes)

    # Add length field (payload length for dynamic mode)
    mode = length_spec.get("mode", "fixed")
    if mode == "dynamic":
        field_def = length_spec.get("field", {})
        ftype = field_def.get("type", "uint8")
        # Length typically represents payload length
        frame.extend(encode_value(len(payload), ftype))

    # Add msg_id
    frame.extend(encode_value(msg_id, "uint8"))

    # Add payload
    frame.extend(payload)

    # Add checksum if specified
    if checksum_spec:
        ctype = checksum_spec["type"]
        rng = checksum_spec["range"]
        store_format = checksum_spec.get("store_format", "uint8")

        # Reserve space for checksum to calculate range correctly
        checksum_len = 1 if store_format == "uint8" else (2 if "16" in store_format else 4)
        total_len = len(frame) + checksum_len

        # Resolve range
        start = rng["from"] if rng["from"] >= 0 else total_len + rng["from"]
        end = rng["to"] if rng["to"] >= 0 else total_len + rng["to"]

        if ctype == "sum8":
            checksum_val = checksum_sum8(bytes(frame), start, min(end, len(frame) - 1))
        elif ctype in ("crc16", "crc32"):
            params = checksum_spec.get("params", {})
            width = 16 if ctype == "crc16" else 32
            checksum_val = crc_compute(
                bytes(frame)[start:min(end + 1, len(frame))],
                width=width,
                poly=params.get("poly", 0),
                init=params.get("init", 0),
                xorout=params.get("xorout", 0),
                refin=params.get("refin", False),
                refout=params.get("refout", False),
            )
        else:
            raise ValueError(f"Unsupported checksum type: {ctype}")

        frame.extend(encode_checksum(checksum_val, store_format))

    return bytes(frame)


def cmd_encode(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    # Load commands.yaml
    if not args.commands:
        raise SystemExit("Missing --commands (expected: spec/command_sets/<command_set_id>/commands.yaml)")
    commands_path = Path(args.commands)
    if not commands_path.is_absolute():
        commands_path = dvk_root / commands_path

    commands_data = load_commands(commands_path)

    # Find command
    command = find_command(commands_data, args.command)
    if command is None:
        available = [c.get("name") for c in commands_data.get("commands", [])]
        raise SystemExit(f"Command not found: {args.command}. Available: {available}")

    # Parse params
    params = {}
    if args.params:
        for p in args.params:
            if "=" not in p:
                raise SystemExit(f"Invalid param format: {p}. Use key=value")
            k, v = p.split("=", 1)
            # Try to parse as number
            try:
                if v.lower().startswith("0x"):
                    params[k] = int(v, 16)
                elif "." in v:
                    params[k] = float(v)
                else:
                    params[k] = int(v)
            except ValueError:
                params[k] = v

    # Build payload
    payload = build_payload(command, params)

    # Output result
    if args.no_frame:
        # Just payload
        result = payload
        print(f"Payload ({len(result)} bytes): {result.hex()}")
    else:
        # Full frame with header, length, checksum
        if not args.protocol:
            raise SystemExit("Missing --protocol (expected: spec/protocols/<protocol_id>/protocol.json)")
        protocol_path = Path(args.protocol)
        if not protocol_path.is_absolute():
            protocol_path = dvk_root / protocol_path

        protocol = load_protocol(protocol_path)
        frames = protocol.get("frames", [])
        if not frames:
            raise SystemExit("protocol.json missing frames[]")

        frame_spec = frames[0]
        if args.frame_name:
            frame_spec = next((f for f in frames if f.get("name") == args.frame_name), None)
            if frame_spec is None:
                raise SystemExit(f"Frame not found: {args.frame_name}")

        header = frame_spec.get("header", [])
        msg_id = command.get("id", 0)
        if isinstance(msg_id, str) and msg_id.startswith("0x"):
            msg_id = int(msg_id, 16)

        result = build_frame(header, msg_id, payload, frame_spec)
        print(f"Frame ({len(result)} bytes): {result.hex()}")

    # Save TX log if requested
    if args.save_tx:
        raw_dir = dvk_root / "data" / "raw" / device_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        tx_path = raw_dir / "tx_frames.bin"

        # Append to existing file
        with tx_path.open("ab") as f:
            f.write(result)
        print(f"Appended to: {tx_path}")

    # JSON output for machine consumption
    if args.json:
        out = {
            "command": command.get("name"),
            "params": params,
            "payload_hex": payload.hex(),
            "frame_hex": result.hex() if not args.no_frame else None,
            "length": len(result),
        }
        print(json.dumps(out, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    """List available commands."""
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    if not args.commands:
        raise SystemExit("Missing --commands (expected: spec/command_sets/<command_set_id>/commands.yaml)")
    commands_path = Path(args.commands)
    if not commands_path.is_absolute():
        commands_path = dvk_root / commands_path

    commands_data = load_commands(commands_path)

    command_set_id = commands_data.get("command_set_id") or commands_data.get("device") or "unknown"
    print(f"Commands for {command_set_id} (device_id={device_id}):")
    for cmd in commands_data.get("commands", []):
        name = cmd.get("name", "?")
        cmd_id = cmd.get("id", "?")
        desc = cmd.get("description", "")
        payload = cmd.get("payload", [])
        params_str = ", ".join(f["name"] for f in payload) if payload else "(none)"
        try:
            cmd_id_hex = f"0x{int(cmd_id):02X}"
        except Exception:
            cmd_id_hex = str(cmd_id)
        print(f"  {name} ({cmd_id_hex}): {desc}")
        print(f"    params: {params_str}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_encode.py", description="Encode commands to protocol frames")
    sub = p.add_subparsers(dest="cmd", required=True)

    # encode subcommand
    enc = sub.add_parser("encode", help="Encode a command to bytes")
    enc.add_argument("--device-id", required=True, help="Device ID")
    enc.add_argument("--command", required=True, help="Command name or hex ID (e.g., ping or 0x01)")
    enc.add_argument("--params", nargs="*", help="Parameters as key=value pairs")
    enc.add_argument("--commands", required=True, help="Path to commands.yaml (e.g., spec/command_sets/<command_set_id>/commands.yaml)")
    enc.add_argument("--protocol", help="Path to protocol.json (required unless --no-frame)")
    enc.add_argument("--frame-name", help="Frame name to use")
    enc.add_argument("--no-frame", action="store_true", help="Output payload only, no framing")
    enc.add_argument("--save-tx", action="store_true", help="Append to tx_frames.bin")
    enc.add_argument("--json", action="store_true", help="Output JSON format")
    enc.set_defaults(func=cmd_encode)

    # list subcommand
    lst = sub.add_parser("list", help="List available commands")
    lst.add_argument("--device-id", required=True, help="Device ID")
    lst.add_argument("--commands", required=True, help="Path to commands.yaml (e.g., spec/command_sets/<command_set_id>/commands.yaml)")
    lst.set_defaults(func=cmd_list)

    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
