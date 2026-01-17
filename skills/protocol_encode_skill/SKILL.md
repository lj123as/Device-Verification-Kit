---
name: protocol_encode_skill
description: This skill encodes business commands/parameters into protocol frames using commands.yaml (and protocol.json for framing/checksum). Requires command selector, params, and protocol assets; request missing inputs before encoding.
---

# protocol_encode_skill

## Purpose
Turn a user-level command into bytes (payload + optional framing/checksum) for debugging, configuration, or automation.

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_serial` | Yes | determines default paths (CLI flag is `--device-id`) |
| Command selector | Yes | command `name` or `id` |
| Command params | Yes | payload field values |
| `commands.yaml` | Yes | `spec/command_sets/{command_set_id}/commands.yaml` (or pass `--commands <path>`) |
| Framing needed? | Yes | if yes, also require `protocol.json` |
| Transport needed? | Optional | if sending immediately, use `transport_session_skill` |

## Outputs
| Output | Path |
|--------|------|
| Encoded frame bytes | (in-memory) |
| Optional TX log | `data/raw/{device_serial}/tx_frames.bin` |

## Data retention (default)
| Artifact | Keep | Path |
|----------|------|------|
| TX frames log | Optional | `data/raw/{device_serial}/tx_frames.bin` |
| Interactive scratch | Optional | `data/tmp/{device_serial}/encode/` |

## Encode tool
| Task | Command |
|------|---------|
| List commands | `python skills/protocol_encode_skill/scripts/dvk_encode.py list --device-id SN-001 --commands spec/command_sets/<command_set_id>/commands.yaml` |
| Encode command | `python skills/protocol_encode_skill/scripts/dvk_encode.py encode --device-id SN-001 --commands spec/command_sets/<command_set_id>/commands.yaml --protocol spec/protocols/<protocol_id>/protocol.json --command ping --params seq=1` |
| Payload only | `python skills/protocol_encode_skill/scripts/dvk_encode.py encode --device-id SN-001 --commands spec/command_sets/<command_set_id>/commands.yaml --command ping --params seq=1 --no-frame` |
| Save TX log | `python skills/protocol_encode_skill/scripts/dvk_encode.py encode --device-id SN-001 --commands spec/command_sets/<command_set_id>/commands.yaml --protocol spec/protocols/<protocol_id>/protocol.json --command ping --params seq=1 --save-tx` |

## Steps (must follow)
1. Confirm `device_serial` and target command
2. Request missing params (do not guess defaults)
3. Build payload using `commands.yaml`
4. (Optional) Wrap into a full frame using `protocol.json` and compute checksum
5. Output bytes (persist TX log if requested)
