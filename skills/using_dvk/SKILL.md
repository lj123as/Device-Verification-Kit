---
name: using_dvk
description: DVK entrypoint skill. This skill orchestrates the end-to-end pipeline (protocol → capture → decode/encode → analysis → report). Use when starting any DVK verification workflow. Requires device serial, protocol selection, transport parameters, and verification goals; request missing inputs before proceeding.
---

# using_dvk (DVK Entry)

## Purpose
`using_dvk` is the single entrypoint for DVK. It validates inputs and orchestrates the end-to-end pipeline:
Protocol assets → Capture & framing → Decode/Encode → Analysis → Report.

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|-------|
| `device_serial` | Yes | Physical unit ID for this run (also used for folder names) |
| Bundle selection | Yes | `{protocol_id + command_set_id}` (and recorded versions), or explicit file paths |
| Protocol assets | Yes | `protocol.json` and (optional) `commands.yaml` |
| Data source | Yes | Live device (UART/Network) or existing raw stream/frames file |
| Desired outputs | Yes | Decode only / Analysis / Report |

## Multi-device runs
| Concept | What it means | Required |
|--------|----------------|----------|
| Device model (`model_id`) | Product model identifier (may map to multiple protocols) | Optional |
| Device instance (`device_serial`) | Physical unit serial/ID for this test run | Yes (for multi-device) |
| Protocol selection | Default is manual; auto-detect only when a model maps to multiple protocols | Yes |

## Protocol selection policy
| Situation | What to do |
|----------|------------|
| New model onboarding | Require transport info + explicit {protocol + commands} bundle; then write/extend `spec/models/<model_id>.yaml` (`protocol_bundles`) |
| `model_id` maps to 1 protocol | Select directly (no detection) |
| `model_id` maps to N>1 protocols | Run `protocol_detection_skill` to propose candidates, then confirm with the user |

## Protocol auto-detection (only for multi-protocol models)
| Method | Description | Typical inputs |
|--------|-------------|----------------|
| A: Query | Send a version/info command and parse response | commands + response schema |
| B: Banner | Parse startup banner text | regex + read window |
| C: Sniff | Passive framing signature detection | header/msg_id/length/checksum |

## Detection tool (UART-first)
| Task | Command |
|------|---------|
| Auto-detect protocol | `python skills/protocol_detection_skill/scripts/dvk_detect_protocol.py uart --device-serial SN-001 --model-id <model_id> --port COM5 --baudrate 115200` |

## Outputs (on disk)
| Output | Path |
|--------|------|
| Protocol assets | `spec/protocols/{protocol_id}/` and `spec/command_sets/{command_set_id}/` |
| Raw capture & frames | `data/raw/{device_serial}/` |
| Decoded/structured data | `data/processed/{device_serial}/` |
| Reports | `reports/{run_id}/` (recommended) or `reports/{device_serial}/` |
| Temporary scratch (optional) | `data/tmp/{device_serial}/` |

## Run records (recommended)
| Artifact | Path |
|----------|------|
| Run template | `runs/run_template.yaml` |
| Model registry | `spec/models/<model_id>.yaml` |
| Detection rules | `spec/detection/rules.yaml` |

## Workflow (must follow)
1. Confirm `device_serial` and (optional) `model_id`
2. If protocol assets are missing: request protocol docs and run `protocol_spec_skill`
3. If raw data is missing: request transport type/params and run `transport_session_skill`
4. Run `protocol_decode_skill` to produce `data/processed/`
5. (Optional) Run `analysis_skill`
6. (Optional) Run `report_skill`

## Rules
| Rule | Why |
|------|-----|
| Ask instead of guessing | Offsets/length/checksum/endianness must be correct |
| Schema-driven only | Do not hardcode protocol parsing rules |
