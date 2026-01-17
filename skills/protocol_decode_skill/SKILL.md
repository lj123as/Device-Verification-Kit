---
name: protocol_decode_skill
description: This skill decodes framed bytes into structured data (CSV/JSON/Parquet) using protocol.json. Requires device serial, protocol selection, frames path, output format, and optional timestamp source; request missing inputs before decoding.
---

# protocol_decode_skill

## Purpose
Parse framed bytes and produce structured records for analysis/reporting.

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_serial` | Yes | determines default paths (CLI flag is `--device-id`) |
| `protocol.json` | Yes | `spec/protocols/{protocol_id}/protocol.json` (or pass `--protocol <path>`) |
| Frames source | Yes | default: `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/raw/frames.bin` |
| Output format | Yes | `csv` / `json` / `parquet` |
| Timestamp source | Optional | from device field / capture time / none |

## Outputs (on disk)
| Output | Path |
|--------|------|
| Raw decoded (byte-level) | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decoded_raw.<csv|json|parquet>` |
| Semantic decoded (analysis-ready) | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decoded.<csv|json|parquet>` |
| Decode metadata | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decode_meta.json` |

## Data retention (default)
| Artifact | Keep | Path |
|----------|------|------|
| Canonical decoded dataset | Yes | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decoded.parquet` (preferred) |
| Raw decoded dataset | Yes | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decoded_raw.parquet` |
| Human-readable export | Yes | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decoded.csv` + `decoded_raw.csv` |
| Decode metadata | Yes | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/processed/decode_meta.json` |

## Decode tool
| Task | Command |
|------|---------|
| Decode (raw + semantic) to CSV | `python skills/protocol_decode_skill/scripts/dvk_decode.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --commands spec/command_sets/<command_set_id>/commands.yaml --format csv` |
| Decode (raw + semantic) to JSON | `python skills/protocol_decode_skill/scripts/dvk_decode.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --commands spec/command_sets/<command_set_id>/commands.yaml --format json` |
| Decode (raw + semantic) to Parquet | `python skills/protocol_decode_skill/scripts/dvk_decode.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --commands spec/command_sets/<command_set_id>/commands.yaml --format parquet` |
| Custom input | `python skills/protocol_decode_skill/scripts/dvk_decode.py --device-id SN-001 --input path/to/frames.bin --protocol path/to/protocol.json` |

## Steps (must follow)
1. Confirm `device_serial` and frames path
2. Load `protocol.json` and validate decoding rules exist
3. Decode fields into records
4. Write outputs to the workdir `.../data/processed/` with basic metadata (units, failures)
