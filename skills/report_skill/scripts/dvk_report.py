#!/usr/bin/env python3
"""
DVK ReportSkill script.

Generates deliverable reports (Markdown/HTML) from analysis outputs and evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_dvk_root(start: Path) -> Path:
    """Find DVK root by locating .claude-plugin/plugin.json marker file."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return parent
    raise SystemExit("Cannot locate DVK root (missing .claude-plugin/plugin.json)")


def load_decode_meta(dvk_root: Path, device_id: str) -> Optional[dict]:
    meta_path = dvk_root / "data" / "processed" / device_id / "decode_meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return None


def load_session_meta(dvk_root: Path, device_id: str) -> Optional[dict]:
    session_path = dvk_root / "data" / "raw" / device_id / "session.json"
    if session_path.exists():
        return json.loads(session_path.read_text(encoding="utf-8"))
    return None


def load_decoded_csv_summary(dvk_root: Path, device_id: str, max_rows: int = 10) -> tuple[List[str], List[List[str]], int]:
    """Load decoded.csv and return (headers, sample_rows, total_count)."""
    csv_path = dvk_root / "data" / "processed" / device_id / "decoded.csv"
    if not csv_path.exists():
        return [], [], 0

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        rows = []
        count = 0
        for row in reader:
            count += 1
            if len(rows) < max_rows:
                rows.append(row)

    return headers, rows, count


def find_figures(reports_dir: Path) -> List[Path]:
    """Find figure files in a reports directory."""
    if not reports_dir.exists():
        return []

    figures: List[Path] = []
    for ext in ["*.png", "*.jpg", "*.svg"]:
        figures.extend(reports_dir.glob(f"**/{ext}"))
    return figures


def generate_markdown_report(
    device_id: str,
    metadata: Dict[str, Any],
    decode_meta: Optional[dict],
    session_meta: Optional[dict],
    csv_summary: tuple,
    figures: List[Path],
    dvk_root: Path,
    protocol_path_display: Optional[str],
    reports_dir: Path
) -> str:
    """Generate Markdown report content."""
    lines = []

    # Title
    lines.append(f"# DVK Verification Report: {device_id}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Overview
    lines.append("## 1. Overview")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|------|-------|")
    lines.append(f"| Device ID | `{device_id}` |")
    for k, v in metadata.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Capture Session
    if session_meta:
        lines.append("## 2. Capture Session")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        stats = session_meta.get("stats", {})
        lines.append(f"| Total Bytes | {stats.get('total_bytes', 'N/A')} |")
        lines.append(f"| Frames OK | {stats.get('frames_ok', 'N/A')} |")
        lines.append(f"| Bad Checksum | {stats.get('frames_bad_checksum', 'N/A')} |")
        lines.append(f"| Resyncs | {stats.get('resyncs', 'N/A')} |")
        lines.append(f"| Checksum Enforced | {session_meta.get('checksum_enforced', 'N/A')} |")
        lines.append(f"| Created | {session_meta.get('created_at', 'N/A')} |")
        lines.append("")

    # Decode Results
    if decode_meta:
        lines.append("## 3. Decode Results")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        stats = decode_meta.get("stats", {})
        lines.append(f"| Total Frames | {stats.get('total_frames', 'N/A')} |")
        lines.append(f"| Decoded OK | {stats.get('decoded_ok', 'N/A')} |")
        lines.append(f"| Decode Errors | {stats.get('decode_errors', 'N/A')} |")
        lines.append(f"| Output Format | {decode_meta.get('format', 'N/A')} |")
        lines.append(f"| Frame Name | {decode_meta.get('frame_name', 'N/A')} |")
        lines.append("")

    # Data Sample
    headers, rows, total_count = csv_summary
    if headers:
        lines.append("## 4. Data Sample")
        lines.append("")
        lines.append(f"Showing first {len(rows)} of {total_count} records.")
        lines.append("")

        # Table header
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Table rows
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        lines.append("")

    # Figures
    if figures:
        lines.append("## 5. Figures")
        lines.append("")
        for fig in figures:
            rel_path = fig.relative_to(dvk_root)
            lines.append(f"![{fig.stem}]({rel_path})")
            lines.append("")

    # Conclusions
    lines.append("## 6. Conclusions")
    lines.append("")
    lines.append("*[Add your conclusions here]*")
    lines.append("")

    # Appendix
    lines.append("## Appendix")
    lines.append("")
    lines.append("### A. File Paths")
    lines.append("")
    lines.append("| Artifact | Path |")
    lines.append("|----------|------|")
    if protocol_path_display:
        lines.append(f"| Protocol | `{protocol_path_display}` |")
    else:
        lines.append("| Protocol | *(not provided)* |")
    lines.append(f"| Raw Data | `data/raw/{device_id}/` |")
    lines.append(f"| Processed Data | `data/processed/{device_id}/` |")
    try:
        reports_rel = reports_dir.relative_to(dvk_root)
        reports_path_display = str(reports_rel).replace(os.sep, "/") + "/"
    except Exception:
        reports_path_display = str(reports_dir)
    lines.append(f"| Reports | `{reports_path_display}` |")
    lines.append("")

    lines.append("---")
    lines.append("*Generated by DVK ReportSkill*")

    return "\n".join(lines)


def generate_html_report(markdown_content: str, device_id: str) -> str:
    """Convert markdown to simple HTML (basic conversion)."""
    lines = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html>")
    lines.append("<head>")
    lines.append(f"<title>DVK Report: {device_id}</title>")
    lines.append("<meta charset='utf-8'>")
    lines.append("<style>")
    lines.append("body { font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }")
    lines.append("table { border-collapse: collapse; width: 100%; margin: 1em 0; }")
    lines.append("th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }")
    lines.append("th { background-color: #f5f5f5; }")
    lines.append("code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }")
    lines.append("h1, h2, h3 { color: #333; }")
    lines.append("img { max-width: 100%; }")
    lines.append("</style>")
    lines.append("</head>")
    lines.append("<body>")

    # Simple markdown to HTML conversion
    in_table = False
    for line in markdown_content.split("\n"):
        if line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("| "):
            if not in_table:
                lines.append("<table>")
                in_table = True
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c == "---" or c.startswith("-") for c in cells):
                continue  # Skip separator row
            tag = "th" if lines[-1] == "<table>" else "td"
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            lines.append(f"<tr>{row}</tr>")
        elif line.startswith("!["):
            # Image
            import re
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if m:
                alt, src = m.groups()
                lines.append(f"<img src='{src}' alt='{alt}'>")
        elif line.startswith("**") and line.endswith("**"):
            lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
        elif line.startswith("*") and line.endswith("*"):
            lines.append(f"<p><em>{line[1:-1]}</em></p>")
        elif line.startswith("---"):
            if in_table:
                lines.append("</table>")
                in_table = False
            lines.append("<hr>")
        elif line.strip() == "":
            if in_table:
                lines.append("</table>")
                in_table = False
        else:
            # Replace inline code
            line = line.replace("`", "<code>", 1) if "`" in line else line
            while "`" in line:
                line = line.replace("`", "</code>", 1)
                if "`" in line:
                    line = line.replace("`", "<code>", 1)
            lines.append(f"<p>{line}</p>")

    if in_table:
        lines.append("</table>")

    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def cmd_generate(args: argparse.Namespace) -> None:
    dvk_root = find_dvk_root(Path(__file__).parent)
    device_id = args.device_id

    reports_dir = Path(args.out_dir) if args.out_dir else (dvk_root / "reports" / device_id)
    if not reports_dir.is_absolute():
        reports_dir = dvk_root / reports_dir

    protocol_path_display: Optional[str] = None
    if args.protocol:
        protocol_path = Path(args.protocol)
        if not protocol_path.is_absolute():
            protocol_path = dvk_root / protocol_path
        try:
            protocol_path_display = str(protocol_path.resolve().relative_to(dvk_root)).replace(os.sep, "/")
        except Exception:
            protocol_path_display = str(protocol_path.resolve())

    # Collect metadata
    metadata = {}
    if args.model:
        metadata["Model"] = args.model
    if args.fw_version:
        metadata["FW Version"] = args.fw_version
    if args.tester:
        metadata["Tester"] = args.tester
    if args.audience:
        metadata["Audience"] = args.audience

    # Load evidence
    decode_meta = load_decode_meta(dvk_root, device_id)
    session_meta = load_session_meta(dvk_root, device_id)
    csv_summary = load_decoded_csv_summary(dvk_root, device_id, max_rows=args.sample_rows)
    figures = find_figures(reports_dir)

    # Generate markdown
    md_content = generate_markdown_report(
        device_id=device_id,
        metadata=metadata,
        decode_meta=decode_meta,
        session_meta=session_meta,
        csv_summary=csv_summary,
        figures=figures,
        dvk_root=dvk_root,
        protocol_path_display=protocol_path_display,
        reports_dir=reports_dir
    )

    # Output directory
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Write output
    fmt = args.format.lower()
    if fmt == "md":
        out_path = reports_dir / "report.md"
        out_path.write_text(md_content, encoding="utf-8")
        print(f"Report generated: {out_path}")
    elif fmt == "html":
        html_content = generate_html_report(md_content, device_id)
        out_path = reports_dir / "report.html"
        out_path.write_text(html_content, encoding="utf-8")
        print(f"Report generated: {out_path}")
    elif fmt == "both":
        md_path = reports_dir / "report.md"
        md_path.write_text(md_content, encoding="utf-8")
        html_content = generate_html_report(md_content, device_id)
        html_path = reports_dir / "report.html"
        html_path.write_text(html_content, encoding="utf-8")
        print(f"Reports generated: {md_path}, {html_path}")
    else:
        raise SystemExit(f"Unsupported format: {fmt}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dvk_report.py", description="Generate DVK verification reports")
    p.add_argument("--device-id", required=True, help="Device ID")
    p.add_argument("--format", choices=["md", "html", "both"], default="md", help="Output format")
    p.add_argument("--protocol", help="Path to protocol.json used for decoding (optional but recommended)")
    p.add_argument(
        "--out-dir",
        help="Output directory (default: reports/{device_id}/). If relative, it is resolved under DVK root.",
    )
    p.add_argument("--model", help="Device model for metadata")
    p.add_argument("--fw-version", help="Firmware version for metadata")
    p.add_argument("--tester", help="Tester name for metadata")
    p.add_argument("--audience", help="Report audience (internal/customer)")
    p.add_argument("--sample-rows", type=int, default=10, help="Number of data sample rows to include")
    return p


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    args = build_parser().parse_args()
    cmd_generate(args)


if __name__ == "__main__":
    main()
