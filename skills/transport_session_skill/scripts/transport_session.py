#!/usr/bin/env python3
"""
DVK TransportSessionSkill scaffold.

Provides:
- Offline framing: stream.bin -> frames.bin (schema-driven via protocol.json)
- Optional serial capture (requires pyserial): COMx -> stream.bin
- Optional network capture (TCP/UDP): socket -> stream.bin
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional, Tuple


def find_dvk_root(start: Path) -> Path:
    """Find DVK root by locating .claude-plugin/plugin.json marker file."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


try:
    _DVK_ROOT = find_dvk_root(Path(__file__).parent)
    sys.path.insert(0, str(_DVK_ROOT))
except Exception:
    _DVK_ROOT = None

from dvk.checksums import verify_checksum  # noqa: E402
from dvk.workdir import default_workdir_root, run_paths  # noqa: E402


def load_protocol(protocol_path: Path) -> dict:
    try:
        return json.loads(protocol_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"protocol.json not found: {protocol_path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {protocol_path}: {e}")


def parse_uint(value_bytes: bytes, value_type: str) -> int:
    if value_type == "uint8":
        if len(value_bytes) != 1:
            raise ValueError("uint8 requires 1 byte")
        return value_bytes[0]
    if value_type == "uint16_le":
        if len(value_bytes) != 2:
            raise ValueError("uint16_le requires 2 bytes")
        return int.from_bytes(value_bytes, "little", signed=False)
    if value_type == "uint16_be":
        if len(value_bytes) != 2:
            raise ValueError("uint16_be requires 2 bytes")
        return int.from_bytes(value_bytes, "big", signed=False)
    if value_type == "uint32_le":
        if len(value_bytes) != 4:
            raise ValueError("uint32_le requires 4 bytes")
        return int.from_bytes(value_bytes, "little", signed=False)
    if value_type == "uint32_be":
        if len(value_bytes) != 4:
            raise ValueError("uint32_be requires 4 bytes")
        return int.from_bytes(value_bytes, "big", signed=False)
    raise ValueError(f"Unsupported length field type: {value_type}")


def resolve_index(index: int, total_len: int) -> int:
    return index if index >= 0 else total_len + index


@dataclass(frozen=True)
class LengthSpec:
    mode: str
    value: Optional[int] = None
    field_offset: Optional[int] = None
    field_length: Optional[int] = None
    field_type: Optional[str] = None
    unit_bytes: Optional[int] = None
    overhead_bytes: Optional[int] = None

    @staticmethod
    def from_frame(frame_spec: dict) -> "LengthSpec":
        length = frame_spec.get("length")
        if not isinstance(length, dict):
            raise ValueError("frame.length must be an object")
        mode = length.get("mode")
        if mode == "fixed":
            return LengthSpec(mode="fixed", value=int(length["value"]))
        if mode == "dynamic":
            field = length.get("field", {})
            return LengthSpec(
                mode="dynamic",
                field_offset=int(field["offset"]),
                field_length=int(field["length"]),
                field_type=str(field["type"]),
                overhead_bytes=int(length["overhead_bytes"]),
            )
        if mode == "counted":
            field = length.get("count_field", {})
            return LengthSpec(
                mode="counted",
                field_offset=int(field["offset"]),
                field_length=int(field["length"]),
                field_type=str(field["type"]),
                unit_bytes=int(length["unit_bytes"]),
                overhead_bytes=int(length["overhead_bytes"]),
            )
        raise ValueError(f"Unsupported length.mode: {mode}")

    def total_length(self, frame_prefix: bytes) -> int:
        if self.mode == "fixed":
            assert self.value is not None
            return self.value
        if self.mode == "counted":
            assert self.field_offset is not None
            assert self.field_length is not None
            assert self.field_type is not None
            assert self.unit_bytes is not None
            assert self.overhead_bytes is not None
            if len(frame_prefix) < self.field_offset + self.field_length:
                return -1
            raw = frame_prefix[self.field_offset : self.field_offset + self.field_length]
            count = parse_uint(raw, self.field_type)
            return (count * self.unit_bytes) + self.overhead_bytes
        assert self.field_offset is not None
        assert self.field_length is not None
        assert self.field_type is not None
        assert self.overhead_bytes is not None
        if len(frame_prefix) < self.field_offset + self.field_length:
            return -1
        raw = frame_prefix[self.field_offset : self.field_offset + self.field_length]
        payload_len = parse_uint(raw, self.field_type)
        return payload_len + self.overhead_bytes


def extract_header(frame_spec: dict) -> bytes:
    header = frame_spec.get("header")
    if not isinstance(header, list) or not header:
        raise ValueError("frame.header must be a non-empty list")
    header_bytes = bytearray()
    for token in header:
        if not isinstance(token, str) or not token.lower().startswith("0x") or len(token) != 4:
            raise ValueError(f"Invalid header byte token: {token!r}")
        header_bytes.append(int(token, 16))
    return bytes(header_bytes)


@dataclass
class FramingStats:
    total_bytes: int = 0
    frames_ok: int = 0
    frames_bad_checksum: int = 0
    resyncs: int = 0


def frame_stream(stream: BinaryIO, frame_spec: dict, out_frames: BinaryIO, enable_checksum: bool) -> FramingStats:
    header = extract_header(frame_spec)
    length_spec = LengthSpec.from_frame(frame_spec)
    checksum_spec = frame_spec.get("checksum")

    stats = FramingStats()
    buf = bytearray()

    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        stats.total_bytes += len(chunk)
        buf.extend(chunk)

        while True:
            idx = buf.find(header)
            if idx < 0:
                if len(buf) > len(header):
                    del buf[: -len(header)]
                break
            if idx > 0:
                stats.resyncs += 1
                del buf[:idx]

            total_len = length_spec.total_length(buf)
            if total_len < 0:
                break
            if len(buf) < total_len:
                break

            frame = bytes(buf[:total_len])
            del buf[:total_len]

            if enable_checksum and isinstance(checksum_spec, dict):
                try:
                    if not verify_checksum(frame, checksum_spec):
                        stats.frames_bad_checksum += 1
                        continue
                except Exception:
                    stats.frames_bad_checksum += 1
                    continue

            out_frames.write(frame)
            stats.frames_ok += 1

    return stats


def cmd_align(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id
    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    run = run_paths(device_id, run_id=args.run_id, workdir_root=workdir_root)

    if not args.protocol:
        raise SystemExit("Missing --protocol (expected: spec/protocols/<protocol_id>/protocol.json)")
    protocol_path = Path(args.protocol)
    if not protocol_path.is_absolute():
        protocol_path = dvk_root / protocol_path
    protocol = load_protocol(protocol_path)

    frames = protocol.get("frames", [])
    if not isinstance(frames, list) or not frames:
        raise SystemExit("protocol.json missing frames[]")
    frame_spec = None
    if args.frame_name is not None:
        frame_spec = next((f for f in frames if f.get("name") == args.frame_name), None)
    elif args.auto_frame_by_if:
        # Select by IF bits using protocol.frame_selector (if_bits_v1).
        selector = protocol.get("frame_selector")
        if isinstance(selector, dict) and selector.get("type") == "if_bits_v1":
            input_path = Path(args.input)
            sample = input_path.read_bytes()[:65535]
            header = extract_header(frames[0])
            idx = sample.find(header)
            if idx >= 0:
                if_offset = int(selector.get("if_offset", 2))
                if idx + if_offset < len(sample):
                    if_byte = sample[idx + if_offset]
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
    if frame_spec is None:
        raise SystemExit(f"Frame not found: {args.frame_name}")

    raw_dir = run.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)
    out_stream_path = raw_dir / "stream.bin"
    if input_path.resolve() != out_stream_path.resolve():
        out_stream_path.write_bytes(input_path.read_bytes())

    out_frames_path = raw_dir / "frames.bin"
    with out_stream_path.open("rb") as fin, out_frames_path.open("wb") as fout:
        stats = frame_stream(fin, frame_spec, fout, enable_checksum=not args.no_checksum)

    session = {
        "device_id": device_id,
        "run_id": run.run_id,
        "workdir": str(workdir_root),
        "protocol": str(protocol_path),
        "frame": frame_spec.get("name"),
        "input": str(out_stream_path),
        "output_frames": str(out_frames_path),
        "checksum_enforced": not args.no_checksum,
        "stats": {
            "total_bytes": stats.total_bytes,
            "frames_ok": stats.frames_ok,
            "frames_bad_checksum": stats.frames_bad_checksum,
            "resyncs": stats.resyncs,
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    (raw_dir / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(session["stats"], ensure_ascii=False))
def cmd_capture_uart(args: argparse.Namespace) -> None:
    try:
        import serial  # type: ignore
    except Exception:
        raise SystemExit("pyserial not installed. Install with: pip install pyserial")

    dvk_root = find_dvk_root(Path(__file__).parent)
    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    run = run_paths(args.device_id, run_id=args.run_id, workdir_root=workdir_root)
    raw_dir = run.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_stream_path = raw_dir / "stream.bin"

    port = args.port
    baudrate = args.baudrate
    duration_s = args.duration_s

    print(f"Capturing UART {port} @ {baudrate} for {duration_s}s -> {out_stream_path}")
    with serial.Serial(port=port, baudrate=baudrate, timeout=0.5) as ser, out_stream_path.open("wb") as fout:
        end = time.time() + duration_s
        while time.time() < end:
            data = ser.read(4096)
            if data:
                fout.write(data)

    print("Capture complete.")


def _capture_socket_stream(
    sock: socket.socket,
    out_stream_path: Path,
    duration_s: int,
    max_bytes: Optional[int],
    recv_chunk: int = 4096,
) -> Tuple[int, int]:
    out_stream_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    chunks = 0
    end = time.time() + duration_s
    with out_stream_path.open("wb") as fout:
        while time.time() < end:
            if max_bytes is not None and total_bytes >= max_bytes:
                break
            try:
                data = sock.recv(recv_chunk)
            except socket.timeout:
                continue
            if not data:
                time.sleep(0.02)
                continue
            chunks += 1
            if max_bytes is not None:
                data = data[: max(0, max_bytes - total_bytes)]
            fout.write(data)
            total_bytes += len(data)
    return total_bytes, chunks


def cmd_capture_tcp(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    run = run_paths(args.device_id, run_id=args.run_id, workdir_root=workdir_root)
    raw_dir = run.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_stream_path = raw_dir / "stream.bin"

    host = args.host
    port = int(args.port)
    duration_s = int(args.duration_s)
    max_bytes = int(args.max_bytes) if args.max_bytes is not None else None
    timeout_s = float(args.timeout_s)

    print(f"Capturing TCP {host}:{port} for {duration_s}s -> {out_stream_path}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout_s)
        sock.connect((host, port))
        total, chunks = _capture_socket_stream(sock, out_stream_path, duration_s, max_bytes)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    print(f"Capture complete. bytes={total}, chunks={chunks}")


def cmd_capture_udp(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    workdir_root = Path(args.workdir).expanduser() if args.workdir else default_workdir_root()
    run = run_paths(args.device_id, run_id=args.run_id, workdir_root=workdir_root)
    raw_dir = run.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_stream_path = raw_dir / "stream.bin"

    bind_host = args.bind_host
    bind_port = int(args.bind_port)
    duration_s = int(args.duration_s)
    max_bytes = int(args.max_bytes) if args.max_bytes is not None else None
    timeout_s = float(args.timeout_s)
    source_host = args.source_host
    source_port = int(args.source_port) if args.source_port is not None else None

    print(f"Capturing UDP {bind_host}:{bind_port} for {duration_s}s -> {out_stream_path}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout_s)
        sock.bind((bind_host, bind_port))
        total_bytes = 0
        datagrams = 0
        end = time.time() + duration_s
        with out_stream_path.open("wb") as fout:
            while time.time() < end:
                if max_bytes is not None and total_bytes >= max_bytes:
                    break
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if not data:
                    continue
                src_h, src_p = addr[0], int(addr[1])
                if source_host and src_h != source_host:
                    continue
                if source_port is not None and src_p != source_port:
                    continue
                datagrams += 1
                if max_bytes is not None:
                    data = data[: max(0, max_bytes - total_bytes)]
                fout.write(data)
                total_bytes += len(data)
        print(f"Capture complete. bytes={total_bytes}, datagrams={datagrams}")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="transport_session.py")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workdir", help="Output workdir root (default: %USERPROFILE%/DVK_Workspaces)")
    common.add_argument("--run-id", help="Run id (default: auto timestamp)")

    sub = p.add_subparsers(dest="cmd", required=True)

    align = sub.add_parser("align", help="Offline: align stream -> frames using protocol.json", parents=[common])
    align.add_argument("--device-id", required=True)
    align.add_argument("--input", required=True, help="Path to raw byte stream (bin)")
    align.add_argument("--protocol", required=True, help="Path to protocol.json (e.g., spec/protocols/<protocol_id>/protocol.json)")
    align.add_argument("--frame-name", help="Frame name to use (default: first frame)")
    align.add_argument("--auto-frame-by-if", action="store_true", help="Auto-select frame by IF bits (requires protocol.frame_selector)")
    align.add_argument("--no-checksum", action="store_true", help="Disable checksum enforcement")
    align.set_defaults(func=cmd_align)

    cap = sub.add_parser("capture-uart", help="Capture UART byte stream to stream.bin (requires pyserial)", parents=[common])
    cap.add_argument("--device-id", required=True)
    cap.add_argument("--port", required=True, help="COMx")
    cap.add_argument("--baudrate", type=int, default=115200)
    cap.add_argument("--duration-s", type=int, default=10)
    cap.set_defaults(func=cmd_capture_uart)

    cap_tcp = sub.add_parser("capture-tcp", help="Capture TCP stream to stream.bin", parents=[common])
    cap_tcp.add_argument("--device-id", required=True)
    cap_tcp.add_argument("--host", required=True)
    cap_tcp.add_argument("--port", required=True, type=int)
    cap_tcp.add_argument("--duration-s", type=int, default=10)
    cap_tcp.add_argument("--timeout-s", type=float, default=0.5)
    cap_tcp.add_argument("--max-bytes", type=int, help="Stop after capturing this many bytes")
    cap_tcp.set_defaults(func=cmd_capture_tcp)

    cap_udp = sub.add_parser("capture-udp", help="Capture UDP datagrams to stream.bin", parents=[common])
    cap_udp.add_argument("--device-id", required=True)
    cap_udp.add_argument("--bind-host", default="0.0.0.0")
    cap_udp.add_argument("--bind-port", required=True, type=int)
    cap_udp.add_argument("--duration-s", type=int, default=10)
    cap_udp.add_argument("--timeout-s", type=float, default=0.5)
    cap_udp.add_argument("--max-bytes", type=int, help="Stop after capturing this many bytes")
    cap_udp.add_argument("--source-host", help="Optional source IP filter")
    cap_udp.add_argument("--source-port", type=int, help="Optional source port filter")
    cap_udp.set_defaults(func=cmd_capture_udp)

    return p


def main() -> None:
    # Improve Windows terminal unicode handling (best-effort).
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
