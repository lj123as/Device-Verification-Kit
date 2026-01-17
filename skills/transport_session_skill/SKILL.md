---
name: transport_session_skill
description: This skill captures bytes from a device (UART-first) and optionally frames them using protocol.json (TransportLayer + SessionLayer). Persists raw stream + framed output under data/raw. Requires device serial, UART params, capture limits, and protocol assets when framing; request missing inputs before capture.
---

# transport_session_skill

## Purpose
Decouple IO from framing:
| Layer | Responsibility |
|------|-----------------|
| **TransportLayer** | reads/writes a byte stream (UART / Network / OfflineFile) |
| **SessionLayer** | frames bytes using `protocol.json` (SOF search, length parsing, resync, optional checksum filter) |

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|-------|
| `device_serial` | Yes | folder name under `data/raw/` (CLI flag is `--device-id`) |
| Transport type | Yes | `UART` (preferred) / `Network` / `OfflineFile` |
| Capture strategy | Yes | duration seconds or max bytes/frames |
| Protocol asset | Only for framing | `spec/protocols/{protocol_id}/protocol.json` (or pass `--protocol <path>`) |

### UART parameters (preferred)
| Param | Required | Example |
|------|----------|---------|
| `port` | Yes | `COM5` |
| `baudrate` | Yes | `115200` |
| `data_bits` | Optional | `8` |
| `stop_bits` | Optional | `1` |
| `parity` | Optional | `none` |

### Network parameters (skeleton)
| Transport | Params | Notes |
|----------|--------|------|
| `TCP` | `host`, `port`, `timeout_s`, `duration_s`, `max_bytes` | writes a continuous stream to `stream.bin` |
| `UDP` | `bind_host`, `bind_port`, `source_host?`, `source_port?`, `timeout_s`, `duration_s`, `max_bytes` | appends each datagram payload to `stream.bin` (no packet boundaries) |

## Outputs (on disk)
| Output | Path |
|--------|------|
| Raw stream | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/raw/stream.bin` |
| Framed output | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/raw/frames.bin` |
| Session metadata | `$DVK_WORKDIR/Device-Verification-Kit/{device_serial}/runs/{run_id}/data/raw/session.json` |

## Temporary / interactive artifacts (optional)
| Artifact | Path | Notes |
|----------|------|------|
| Live session scratch | `data/tmp/{device_serial}/transport/` | logs, quick captures, experiments |

## Steps (must follow)
1. Confirm `device_serial` and transport type
2. Request missing transport params (do not guess)
3. Capture byte stream to `stream.bin`
4. If framing is requested: load `protocol.json` and extract header/length/checksum rules
5. Frame it to `frames.bin` and record stats to `session.json`

## Checksum support
Checksum validation is schema-driven via `protocol.json`:
| Type | Notes |
|------|------|
| `sum8` | requires `store_at`, optional `store_format=uint8` |
| `crc16` / `crc32` | requires `store_format` and `params` (poly/init/xorout/refin/refout) |

## Reference Script (runnable)
| Command | What it does |
|--------|--------------|
| `python skills/transport_session_skill/scripts/transport_session.py capture-uart --device-id SN-001 --port COMx --baudrate 115200 --duration-s 10` | Capture UART stream |
| `python skills/transport_session_skill/scripts/transport_session.py capture-tcp --device-id SN-001 --host 192.168.1.10 --port 9000 --duration-s 10` | Capture TCP stream |
| `python skills/transport_session_skill/scripts/transport_session.py capture-udp --device-id SN-001 --bind-port 9001 --duration-s 10` | Capture UDP datagrams (payload concat) |
| `python skills/transport_session_skill/scripts/transport_session.py align --device-id SN-001 --input path/to/stream.bin --protocol spec/protocols/<protocol_id>/protocol.json` | Offline framing (stream → frames) |

## TransportLayer Extension
When adding a new transport:
| Rule | Notes |
|------|------|
| Adapter does IO only | no framing logic inside adapter |
| Keep a minimal interface | `open/close/read/write` (write optional) |
| Request params from user | if the parameter set is unclear |
