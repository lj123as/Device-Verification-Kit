---
name: protocol_detection_skill
description: This skill auto-detects the correct DVK protocol for a device instance (multi-device runs) using UART-first A/B/C methods (A=query, B=banner, C=sniff). Records device serial/ID and detection evidence under runs/ and data/tmp. Use when model maps to multiple protocols; request missing transport params before detection.
---

# protocol_detection_skill

## Purpose
Propose `protocol_id@protocol_version` for a **device instance** (serial/ID) and persist a run record with evidence.

## When to use (policy)
| Situation | Use this skill? |
|----------|------------------|
| User already specified protocol | No (skip detection) |
| `model_id` maps to 1 protocol | No (select directly) |
| `model_id` maps to N>1 protocols | Yes (recommend) |
| Model unknown + user explicitly wants detection | Yes (but expect ambiguity) |

## Concepts
| Concept | Meaning |
|--------|---------|
| `device_serial` | Physical unit identifier used in tests (multi-device) |
| `model_id` | Optional device model (many-to-many with protocols) |
| ProtocolSpec | Protocol assets keyed by `protocol_id` + `protocol_version` |

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_serial` | Yes | e.g. `SN-001` |
| Transport | Yes | UART-first in this repo |
| UART params | Yes | `port`, `baudrate` |
| Detection rules | Optional | `spec/detection/rules.yaml` (query + banner) |
| Model file | Recommended | `spec/models/<model_id>.yaml` (`protocol_bundles`) |

## Outputs
| Artifact | Path |
|----------|------|
| Run record | `runs/<run_id>.yaml` |
| Evidence | `data/tmp/<device_serial>/detection/<run_id>/` |

## Detection methods (C is the default preference)
| Method | What it does | Typical requirement |
|--------|--------------|---------------------|
| A: Query | send a probe command and parse response | defined query tx/rx rule |
| B: Banner | read startup text and regex-match | banner regex |
| C: Sniff | read bytes and score protocol candidates using `protocol.json` (framing + checksum) | protocol assets in `spec/protocols/**/protocol.json` |

## Command (UART-first)
| Task | Command |
|------|---------|
| Detect and write run record | `python skills/protocol_detection_skill/scripts/dvk_detect_protocol.py uart --device-serial SN-001 --port COM5 --baudrate 115200` |
| Restrict by model | `python ... uart --device-serial SN-001 --model-id <model_id> --port COM5 --baudrate 115200` |
| Append to existing run | `python ... uart --run-file runs/<run_id>.yaml --device-serial ...` |
| Offline test | `python skills/protocol_detection_skill/scripts/dvk_detect_protocol.py file --device-serial SN-001 --sample sample.bin` |

## Rule files
| File | Role |
|------|------|
| `spec/detection/rules.yaml` | A/B detection rules (query + banner); sniff uses protocol assets |
| `spec/models/<model_id>.yaml` | model-scoped bundle list (candidate restriction) |

## Candidate selection logic
| Situation | Candidate set |
|----------|---------------|
| `model_id` provided | protocols from `spec/models/<model_id>.yaml` |
| `model_id` not provided | scan all `spec/protocols/**/protocol.json` |
| model maps to a single protocol | select directly (skip sniff) |

## Notes
| Item | Meaning |
|------|---------|
| Sniff uses protocol assets | `spec/protocols/**/protocol.json` defines headers/length/checksum |
| Rules file is optional | `spec/detection/rules.yaml` is only for query/banner; no hardcoded sniff rules |

## Behavior rules
| Rule | Why |
|------|-----|
| Prefer C, but allow A/B | most devices are sniff-able; A/B improves confidence |
| Persist evidence | auditability and reproducibility |
| If ambiguous, stop and ask | do not guess protocol |
