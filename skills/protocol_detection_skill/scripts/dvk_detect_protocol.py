#!/usr/bin/env python3
"""
DVK Protocol Detection (UART-first).

Applies A/B/C rules from:
- spec/detection/rules.yaml
- spec/models/<model_id>.yaml (optional candidate restriction)

Writes a run record (YAML) under runs/ and evidence under data/tmp/.

This repo does NOT bundle Python packages. Install dependencies yourself:
  pip install -r skills/protocol_detection_skill/requirements.txt
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _require_yaml() -> Any:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: PyYAML\n"
            "Install: pip install -r skills/protocol_detection_skill/requirements.txt\n"
            f"Error: {e}"
        )
    return yaml


def _require_serial() -> Any:
    try:
        import serial  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: pyserial\n"
            "Install: pip install -r skills/protocol_detection_skill/requirements.txt\n"
            f"Error: {e}"
        )
    return serial


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


def load_yaml(path: Path) -> dict:
    yaml = _require_yaml()
    if not path.exists():
        raise SystemExit(f"YAML not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, obj: dict) -> None:
    yaml = _require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True), encoding="utf-8")


def parse_hex_bytes(tokens: List[str]) -> bytes:
    out = bytearray()
    for t in tokens:
        if not isinstance(t, str) or not t.lower().startswith("0x") or len(t) != 4:
            raise ValueError(f"Invalid hex byte token: {t!r}")
        out.append(int(t, 16))
    return bytes(out)


@dataclass(frozen=True)
class DetectionResult:
    protocol_id: Optional[str]
    protocol_version: Optional[str]
    model_id: Optional[str]
    confidence: float
    rule_id: str
    method: str


def load_protocol_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"protocol.json not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {path}: {e}")


def list_protocol_candidates(dvk_root: Path) -> List[Tuple[str, str, Path]]:
    """
    Return [(protocol_id, protocol_version, protocol_json_path)].
    Layout:
    - spec/protocols/<protocol_id>/protocol.json
    (protocol_version is stored inside protocol.json)
    """
    base = dvk_root / "spec" / "protocols"
    paths = list(base.rglob("protocol.json"))
    out: List[Tuple[str, str, Path]] = []
    for p in paths:
        rel = p.relative_to(base)
        parts = rel.parts
        protocol_id = parts[0] if parts else "unknown"
        protocol_version = "unknown"
        try:
            doc = load_protocol_json(p)
            protocol_id = str(doc.get("protocol_id") or protocol_id)
            protocol_version = str(doc.get("protocol_version") or protocol_version)
        except SystemExit:
            continue
        out.append((protocol_id, protocol_version, p))
    return out


def load_model_doc(dvk_root: Path, model_id: str) -> dict:
    path = dvk_root / "spec" / "models" / f"{model_id}.yaml"
    if not path.exists():
        return {}
    return load_yaml(path)


def protocol_refs_for_model(model_doc: dict) -> List[Tuple[str, Optional[str]]]:
    bundles = model_doc.get("protocol_bundles", [])
    if not isinstance(bundles, list):
        return []
    out: List[Tuple[str, Optional[str]]] = []
    for b in bundles:
        if not isinstance(b, dict):
            continue
        pid = b.get("protocol_id")
        if not pid:
            continue
        expected_ver = b.get("expected_protocol_version")
        out.append((str(pid), str(expected_ver) if expected_ver else None))
    return out


def resolve_index(index: int, total_len: int) -> int:
    return index if index >= 0 else total_len + index


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


def extract_header(frame_spec: dict) -> bytes:
    header = frame_spec.get("header")
    if not isinstance(header, list) or not header:
        raise ValueError("frame.header must be a non-empty list")
    out = bytearray()
    for token in header:
        t = str(token)
        if not t.lower().startswith("0x") or len(t) != 4:
            raise ValueError(f"Invalid header token: {token!r}")
        out.append(int(t, 16))
    return bytes(out)


def parse_length_spec(frame_spec: dict) -> dict:
    length = frame_spec.get("length")
    if isinstance(length, dict):
        return length
    # legacy fallback (very limited)
    if length == "fixed":
        return {"mode": "fixed", "value": int(frame_spec.get("total_length", 0))}
    raise ValueError("frame.length must be an object")


def iter_frames(sample: bytes, frame_spec: dict, enable_checksum: bool) -> Tuple[int, int, int]:
    """
    Returns (frames_ok, frames_bad_checksum, resyncs) for this frame_spec.
    """
    header = extract_header(frame_spec)
    length = parse_length_spec(frame_spec)
    checksum_spec = frame_spec.get("checksum") if enable_checksum else None

    buf = bytearray(sample)
    ok = 0
    bad = 0
    resyncs = 0

    while True:
        idx = buf.find(header)
        if idx < 0:
            break
        if idx > 0:
            resyncs += 1
            del buf[:idx]

        total_len = -1
        if length.get("mode") == "fixed":
            total_len = int(length.get("value", -1))
        elif length.get("mode") == "dynamic":
            field = length.get("field", {})
            off = int(field.get("offset", -1))
            ln = int(field.get("length", -1))
            tp = str(field.get("type", ""))
            overhead = int(length.get("overhead_bytes", 0))
            if off >= 0 and ln > 0 and len(buf) >= off + ln:
                payload_len = parse_uint(bytes(buf[off : off + ln]), tp)
                total_len = payload_len + overhead
        elif length.get("mode") == "counted":
            field = length.get("count_field", {})
            off = int(field.get("offset", -1))
            ln = int(field.get("length", -1))
            tp = str(field.get("type", ""))
            overhead = int(length.get("overhead_bytes", 0))
            unit_bytes = int(length.get("unit_bytes", 0))
            if off >= 0 and ln > 0 and len(buf) >= off + ln:
                count = parse_uint(bytes(buf[off : off + ln]), tp)
                total_len = (count * unit_bytes) + overhead
        if total_len <= 0 or len(buf) < total_len:
            break

        frame = bytes(buf[:total_len])
        del buf[:total_len]

        if checksum_spec and isinstance(checksum_spec, dict):
            try:
                if not verify_checksum(frame, checksum_spec):
                    bad += 1
                    continue
            except Exception:
                bad += 1
                continue

        ok += 1

    return ok, bad, resyncs


def match_banner(rule: dict, banner_text: str) -> Tuple[Optional[DetectionResult], Dict[str, str]]:
    match_cfg = rule.get("match", {})
    regex = match_cfg.get("regex")
    if not regex:
        return None, {}
    m = re.search(regex, banner_text, flags=re.MULTILINE)
    if not m:
        return None, {}

    groups = {k: v for k, v in m.groupdict().items() if v is not None}
    out_cfg = rule.get("outputs", {})
    model_id = out_cfg.get("model_id")
    if isinstance(model_id, str) and model_id.startswith("$"):
        model_id = groups.get(model_id[1:])
    confidence = float(rule.get("confidence", 0.5))
    return (
        DetectionResult(
            protocol_id=out_cfg.get("protocol_id"),
            protocol_version=out_cfg.get("protocol_version"),
            model_id=model_id,
            confidence=confidence,
            rule_id=str(rule.get("id", "banner_rule")),
            method="banner",
        ),
        groups,
    )


def sniff_score_protocol(protocol_json_path: Path, sample: bytes) -> Tuple[int, int, int]:
    doc = load_protocol_json(protocol_json_path)
    frames = doc.get("frames", [])
    if not isinstance(frames, list) or not frames:
        return 0, 0, 0

    ok = 0
    bad = 0
    resyncs = 0
    for f in frames:
        if not isinstance(f, dict):
            continue
        f_ok, f_bad, f_resyncs = iter_frames(sample, f, enable_checksum=True)
        ok += f_ok
        bad += f_bad
        resyncs += f_resyncs
    return ok, bad, resyncs


def score_to_confidence(frames_ok: int, frames_bad: int) -> float:
    total = frames_ok + frames_bad
    if total <= 0:
        return 0.0
    return min(0.99, 0.2 + 0.79 * (frames_ok / (total + 1e-9)))


def pick_by_sniff(
    candidates: List[Tuple[str, str, Path]], sample: bytes
) -> Tuple[Optional[DetectionResult], List[dict], bool]:
    scored: List[dict] = []
    for pid, ver, path in candidates:
        ok, bad, resyncs = sniff_score_protocol(path, sample)
        score = ok * 100 - bad * 50 - resyncs
        scored.append(
            {
                "protocol_id": pid,
                "protocol_version": ver,
                "protocol_json": str(path),
                "frames_ok": ok,
                "frames_bad_checksum": bad,
                "resyncs": resyncs,
                "score": score,
            }
        )
    scored.sort(key=lambda x: int(x["score"]), reverse=True)
    if not scored or scored[0]["frames_ok"] <= 0:
        return None, scored, False

    best = scored[0]
    ambiguous = False
    if len(scored) > 1 and scored[1]["frames_ok"] > 0:
        # If second-best is too close, treat as ambiguous.
        if best["score"] - scored[1]["score"] < 50:
            ambiguous = True

    res = DetectionResult(
        protocol_id=best["protocol_id"],
        protocol_version=best["protocol_version"],
        model_id=None,
        confidence=score_to_confidence(int(best["frames_ok"]), int(best["frames_bad_checksum"])),
        rule_id="sniff_protocol_assets" + (":ambiguous" if ambiguous else ""),
        method="sniff",
    )
    return res, scored, ambiguous


def apply_query_rule(rule: dict, ser: Any) -> Optional[DetectionResult]:
    """
    Minimal query rule support:
    rule.query.tx_hex: ["0xAA", ...]
    rule.query.rx_regex: "..."
    """
    query = rule.get("query", {})
    tx = query.get("tx_hex")
    rx_regex = query.get("rx_regex")
    if not isinstance(tx, list) or not rx_regex:
        return None

    payload = parse_hex_bytes([str(x) for x in tx])
    ser.reset_input_buffer()
    ser.write(payload)
    ser.flush()

    timeout_ms = int(query.get("timeout_ms", 800))
    end = time.time() + timeout_ms / 1000.0
    chunks: List[bytes] = []
    while time.time() < end:
        data = ser.read(4096)
        if data:
            chunks.append(data)
            text = b"".join(chunks).decode("utf-8", errors="ignore")
            m = re.search(rx_regex, text, flags=re.MULTILINE)
            if m:
                groups = {k: v for k, v in m.groupdict().items() if v is not None}
                out_cfg = rule.get("outputs", {})
                protocol_id = out_cfg.get("protocol_id") or groups.get("protocol_id")
                protocol_version = out_cfg.get("protocol_version") or groups.get("protocol_version")
                model_id = out_cfg.get("model_id") or groups.get("model_id")
                confidence = float(rule.get("confidence", 0.9))
                return DetectionResult(
                    protocol_id=protocol_id,
                    protocol_version=protocol_version,
                    model_id=model_id,
                    confidence=confidence,
                    rule_id=str(rule.get("id", "query_rule")),
                    method="query",
                )
        time.sleep(0.02)
    return None


def choose_best(results: List[DetectionResult]) -> Optional[DetectionResult]:
    if not results:
        return None
    # Sort by confidence desc, then prefer sniff over banner over query only if confidence ties.
    method_rank = {"sniff": 2, "banner": 1, "query": 0}
    results_sorted = sorted(results, key=lambda r: (r.confidence, method_rank.get(r.method, 0)), reverse=True)
    return results_sorted[0]


def ensure_run_id(run_id: Optional[str]) -> str:
    if run_id:
        return run_id
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_evidence_dir(dvk_root: Path, device_serial: str, run_id: str) -> Path:
    d = dvk_root / "data" / "tmp" / device_serial / "detection" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_or_init_run(run_file: Path, run_id: str) -> dict:
    yaml = _require_yaml()
    if run_file.exists():
        return yaml.safe_load(run_file.read_text(encoding="utf-8")) or {}
    return {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "operator": "",
        "test_plan_id": "",
        "devices": [],
        "artifacts": {},
    }


def append_device(run: dict, device_entry: dict) -> None:
    run.setdefault("devices", [])
    run["devices"].append(device_entry)


def cmd_uart(args: argparse.Namespace) -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    serial = _require_serial()
    dvk_root = find_dvk_root(Path(__file__).parent)

    device_serial = args.device_serial
    run_id = ensure_run_id(args.run_id)
    evidence_dir = ensure_evidence_dir(dvk_root, device_serial, run_id)

    rules_path = Path(args.rules) if args.rules else (dvk_root / "spec" / "detection" / "rules.yaml")
    rules_doc = load_yaml(rules_path) if rules_path.exists() else {}
    rules = rules_doc.get("rules", [])
    if not isinstance(rules, list):
        raise SystemExit("spec/detection/rules.yaml must contain a top-level 'rules' list")

    # Filter UART rules (query/banner only) and sort by priority.
    uart_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        inputs = r.get("inputs", {})
        transport = (inputs.get("transport") or "UART").upper()
        if transport == "UART":
            uart_rules.append(r)
    uart_rules.sort(key=lambda r: int(r.get("priority", 1000)))

    # Open UART once for banner/sniff/query.
    with serial.Serial(port=args.port, baudrate=args.baudrate, timeout=0.2) as ser:
        # Banner capture (max window across banner rules).
        banner_ms = 0
        for r in uart_rules:
            if r.get("method") == "banner":
                banner_ms = max(banner_ms, int((r.get("inputs") or {}).get("read_window_ms", 0)))
        banner_text = ""
        if banner_ms > 0:
            end = time.time() + banner_ms / 1000.0
            chunks: List[bytes] = []
            while time.time() < end:
                data = ser.read(4096)
                if data:
                    chunks.append(data)
                time.sleep(0.02)
            banner_text = b"".join(chunks).decode("utf-8", errors="ignore")
            (evidence_dir / "banner.txt").write_text(banner_text, encoding="utf-8")

        # Sniff capture (fixed minimum; sniff uses protocol assets, not rules).
        sniff_min = int(args.sample_bytes)
        sniff_bytes = b""
        if sniff_min > 0:
            chunks = []
            while sum(len(c) for c in chunks) < sniff_min:
                data = ser.read(4096)
                if data:
                    chunks.append(data)
                else:
                    time.sleep(0.02)
            sniff_bytes = b"".join(chunks)
            (evidence_dir / "sniff.bin").write_bytes(sniff_bytes)

        results: List[DetectionResult] = []
        matched_groups: Dict[str, str] = {}
        for rule in uart_rules:
            method = str(rule.get("method", "")).lower()
            if method == "query":
                res = apply_query_rule(rule, ser)
                if res:
                    results.append(res)
            elif method == "banner" and banner_text:
                res, groups = match_banner(rule, banner_text)
                if res:
                    results.append(res)
                    matched_groups.update(groups)

        # If query produced an explicit protocol, prefer it.
        best = choose_best([r for r in results if r.method == "query"])

        model_id = args.model_id or matched_groups.get("model_id") or (best.model_id if best else None)

        candidates = list_protocol_candidates(dvk_root)
        if model_id:
            model_doc = load_model_doc(dvk_root, model_id)
            refs = protocol_refs_for_model(model_doc)
            allowed_ids = {pid for pid, _ in refs}
            if allowed_ids:
                candidates = [c for c in candidates if c[0] in allowed_ids]
                # If the model specifies an expected version, filter by it.
                expected_by_id = {pid: ver for pid, ver in refs if ver}
                if expected_by_id:
                    candidates = [
                        c for c in candidates
                        if (c[0] not in expected_by_id) or (c[1] == expected_by_id[c[0]])
                    ]
                # If only one protocol is compatible, select without sniffing.
                if len(candidates) == 1 and not best:
                    pid, ver, _ = candidates[0]
                    best = DetectionResult(
                        protocol_id=pid,
                        protocol_version=ver,
                        model_id=model_id,
                        confidence=0.9,
                        rule_id="model_file_single",
                        method="model_file",
                    )

        sniff_scored: List[dict] = []
        sniff_ambiguous = False
        if not best:
            sniff_best, sniff_scored, sniff_ambiguous = pick_by_sniff(
                [(pid, ver, p) for pid, ver, p in candidates], sniff_bytes
            )
            best = sniff_best

        if not best:
            raise SystemExit(
                "Protocol not detected.\n"
                f"- Rules: {rules_path if rules_path.exists() else '<none>'}\n"
                f"- Evidence: {evidence_dir}\n"
                "Provide additional protocol assets or specify model_id / protocol manually."
            )

    # Build / append run record.
    run_file = Path(args.run_file) if args.run_file else (dvk_root / "runs" / f"{run_id}.yaml")
    run = load_or_init_run(run_file, run_id)

    device_entry: Dict[str, Any] = {
        "device_serial": device_serial,
        "model_id": (best.model_id or matched_groups.get("model_id") or args.model_id or ""),
        "transport": {
            "type": "UART",
            "port": args.port,
            "baudrate": args.baudrate,
        },
        "detection": {
            "mode": "auto",
            "detected": {
                "protocol_id": best.protocol_id or "",
                "protocol_version": best.protocol_version or "",
                "confidence": float(best.confidence),
                "rule_id": best.rule_id,
                "method": best.method,
            },
            "evidence": {
                "banner_log": str((evidence_dir / "banner.txt")) if (evidence_dir / "banner.txt").exists() else "",
                "sniff_sample": str((evidence_dir / "sniff.bin")) if (evidence_dir / "sniff.bin").exists() else "",
            },
        },
    }
    if sniff_scored:
        device_entry["detection"]["candidates"] = sniff_scored[:10]
        device_entry["detection"]["ambiguous"] = bool(sniff_ambiguous)

    # If sniff is ambiguous and user didn't allow it, write run record but force manual decision.
    if device_entry["detection"].get("ambiguous") and not args.allow_ambiguous and best.method == "sniff":
        device_entry["detection"]["detected"] = {
            "protocol_id": "",
            "protocol_version": "",
            "confidence": 0.0,
            "rule_id": "ambiguous",
            "method": "sniff",
        }
        device_entry["detection"]["recommendations"] = [
            f"{c['protocol_id']}@{c['protocol_version']}" for c in (sniff_scored[:5] if sniff_scored else [])
        ]
        append_device(run, device_entry)
        dump_yaml(run_file, run)
        print(f"run_file: {run_file}")
        print(f"device_serial: {device_serial}")
        print("Ambiguous sniff result. Provide --model-id to restrict candidates, or choose one protocol manually.")
        raise SystemExit(2)
    append_device(run, device_entry)
    dump_yaml(run_file, run)

    print(f"run_file: {run_file}")
    print(f"device_serial: {device_serial}")
    print(f"detected: {best.protocol_id}@{best.protocol_version} (confidence={best.confidence}, rule={best.rule_id}, method={best.method})")


def cmd_file(args: argparse.Namespace) -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    dvk_root = find_dvk_root(Path(__file__).parent)

    device_serial = args.device_serial
    run_id = ensure_run_id(args.run_id)
    evidence_dir = ensure_evidence_dir(dvk_root, device_serial, run_id)

    sample_path = Path(args.sample)
    if not sample_path.exists():
        raise SystemExit(f"Sample not found: {sample_path}")
    sample = sample_path.read_bytes()
    (evidence_dir / "sniff.bin").write_bytes(sample)

    model_id = args.model_id
    candidates = list_protocol_candidates(dvk_root)
    if model_id:
        model_doc = load_model_doc(dvk_root, model_id)
        refs = protocol_refs_for_model(model_doc)
        allowed_ids = {pid for pid, _ in refs}
        if allowed_ids:
            candidates = [c for c in candidates if c[0] in allowed_ids]
            expected_by_id = {pid: ver for pid, ver in refs if ver}
            if expected_by_id:
                candidates = [
                    c for c in candidates
                    if (c[0] not in expected_by_id) or (c[1] == expected_by_id[c[0]])
                ]

    sniff_best, sniff_scored, sniff_ambiguous = pick_by_sniff([(pid, ver, p) for pid, ver, p in candidates], sample)
    if not sniff_best:
        raise SystemExit(f"Protocol not detected from sample. Evidence: {evidence_dir}")

    run_file = Path(args.run_file) if args.run_file else (dvk_root / "runs" / f"{run_id}.yaml")
    run = load_or_init_run(run_file, run_id)

    device_entry: Dict[str, Any] = {
        "device_serial": device_serial,
        "model_id": model_id or "",
        "transport": {"type": "OfflineFile", "sample": str(sample_path)},
        "detection": {
            "mode": "offline",
            "detected": {
                "protocol_id": sniff_best.protocol_id or "",
                "protocol_version": sniff_best.protocol_version or "",
                "confidence": float(sniff_best.confidence),
                "rule_id": sniff_best.rule_id,
                "method": sniff_best.method,
            },
            "evidence": {"sniff_sample": str((evidence_dir / "sniff.bin"))},
            "candidates": sniff_scored[:10],
            "ambiguous": bool(sniff_ambiguous),
        },
    }

    if device_entry["detection"].get("ambiguous") and not args.allow_ambiguous:
        device_entry["detection"]["detected"] = {
            "protocol_id": "",
            "protocol_version": "",
            "confidence": 0.0,
            "rule_id": "ambiguous",
            "method": "sniff",
        }
        device_entry["detection"]["recommendations"] = [
            f"{c['protocol_id']}@{c['protocol_version']}" for c in (sniff_scored[:5] if sniff_scored else [])
        ]
        append_device(run, device_entry)
        dump_yaml(run_file, run)
        print(f"run_file: {run_file}")
        print(f"device_serial: {device_serial}")
        print("Ambiguous sniff result. Provide --model-id to restrict candidates, or choose one protocol manually.")
        raise SystemExit(2)

    append_device(run, device_entry)
    dump_yaml(run_file, run)
    print(f"run_file: {run_file}")
    print(f"device_serial: {device_serial}")
    print(f"detected: {sniff_best.protocol_id}@{sniff_best.protocol_version} (confidence={sniff_best.confidence}, rule={sniff_best.rule_id}, method={sniff_best.method})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_detect_protocol.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    uart = sub.add_parser("uart", help="UART-first protocol detection (A/B/C rules)")
    uart.add_argument("--device-serial", required=True)
    uart.add_argument("--model-id", help="Optional model_id to restrict protocol candidates")
    uart.add_argument("--port", required=True)
    uart.add_argument("--baudrate", type=int, default=115200)
    uart.add_argument("--sample-bytes", type=int, default=2048, help="Sniff sample size (bytes)")
    uart.add_argument("--rules", help="Path to detection rules.yaml (banner/query only)")
    uart.add_argument("--allow-ambiguous", action="store_true", help="Allow ambiguous sniff results")
    uart.add_argument("--run-id", help="Optional run id (default: timestamp)")
    uart.add_argument("--run-file", help="Append to an existing run YAML (or create)")
    uart.set_defaults(func=cmd_uart)

    filecmd = sub.add_parser("file", help="Offline detection from a captured sample.bin (no hardware)")
    filecmd.add_argument("--device-serial", required=True)
    filecmd.add_argument("--model-id", help="Optional model_id to restrict protocol candidates")
    filecmd.add_argument("--sample", required=True, help="Path to captured bytes (bin)")
    filecmd.add_argument("--allow-ambiguous", action="store_true", help="Allow ambiguous sniff results")
    filecmd.add_argument("--run-id", help="Optional run id (default: timestamp)")
    filecmd.add_argument("--run-file", help="Append to an existing run YAML (or create)")
    filecmd.set_defaults(func=cmd_file)

    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
