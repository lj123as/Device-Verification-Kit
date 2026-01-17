---
name: protocol_spec_skill
description: This skill converts protocol documentation (PDF/images/Word) into DVK protocol assets (protocol.json + commands.yaml). Use for onboarding new protocols and freezing final schemas. Requires header/length/checksum/endianness details; request missing critical information before generating assets.
---

# protocol_spec_skill

## Purpose
Extract protocol definitions from unstructured docs and produce DVK assets consumed by downstream skills:
| Asset | Role |
|------|------|
| `protocol.json` | machine-friendly framing/length/checksum/types (bytes-only) |
| `commands.yaml` | human-friendly commands/params/units/ranges/notes |

## Transport binding policy
| Item | Policy |
|------|--------|
| `protocol.json` | transport-agnostic (pure framing/bytes) |
| Device model | binds transport (UART/I2C/SPI/Network) via `spec/models/<model_id>.yaml` |

## Output Schemas (must follow)
| Asset | Schema |
|------|--------|
| `protocol.json` | `spec/schemas/protocol.schema.json` |
| `commands.yaml` | `spec/schemas/commands.schema.json` |

## Required Inputs (ask if missing)
| Item | Required | What you need from the user |
|------|----------|------------------------------|
| `protocol_id` | Yes | protocol identifier (folder name under `spec/protocols/`) |
| `protocol_version` | Yes | version is stored inside `protocol.json` (not in the path) |
| `command_set_id` | Yes | command set identifier (folder name under `spec/command_sets/`) |
| `command_set_version` | Yes | version is stored inside `commands.yaml` (not in the path) |
| `model_id` | Recommended | device model identifier for transport binding |
| Transport info | Yes (onboarding model) | interface type(s) + default params (UART port/baudrate, etc.) |
| Protocol docs | Yes | file path or key screenshots/sections |
| Frame definitions | Yes | header bytes, length rule (fixed/dynamic), overhead bytes |
| Frame selector | Optional | if IF/flags change framing, define `frame_selector` and provide bit positions |
| Field table | Yes | `name`, `offset`, `length`, `type` (endianness included in type) |
| Checksum | If used | algorithm + range + where stored + CRC variant params |
| Commands | Optional | command id/name + payload fields + ranges/defaults/enums |

## CRC variants (crc16/crc32)
If the protocol uses CRC, you MUST request the variant parameters and encode them into `protocol.json`:
| Key | Meaning |
|-----|---------|
| `store_format` | `uint16_le/uint16_be/uint32_le/uint32_be` |
| `params.poly` | polynomial (integer) |
| `params.init` | initial value |
| `params.xorout` | final XOR value |
| `params.refin` | reflect input bytes |
| `params.refout` | reflect output CRC |

Note: For reflected CRCs (`refin=true`), provide the reflected polynomial value (common for CRC-32: `0xEDB88320`).

## Checksum handling (strict policy)
### Supported checksum types
`protocol.json` checksum MUST use one of these `checksum.type` values:
| `checksum.type` | Typical use | Where defined |
|---|---|---|
| `sum8` | Simple byte sum | `dvk/checksums.py` |
| `cs15` | Spec-defined “CS15” style folding checksum | `dvk/checksums.py` |
| `xor16_slices` | XOR16 over configurable byte slices (protocol-defined) | `dvk/checksums.py` + `protocol.json checksum.params` |
| `crc16` / `crc32` | Parameterized CRC variants | `dvk/checksums.py` + `protocol.json checksum.params` |

### Required checksum inputs (ask if missing)
| Item | Required | Notes |
|---|---:|---|
| Algorithm family | Yes | sum / xor / crc / custom |
| Byte order | Yes | how checksum bytes are stored (`store_format`) |
| Stored position | Yes | `store_at` offset (can be negative tail offset) |
| Range included | Yes | `range.from` + `range.to` (inclusive) |
| Exclusions | Yes | confirm whether checksum bytes themselves are excluded |
| CRC params | If CRC | poly/init/xorout/refin/refout |
| XOR slice params | If XOR16 | seed offsets + slice start/end/stride + rel offsets |

### When a new checksum appears (extension workflow)
1. Try to map it to an existing checksum type above (prefer `crc*` or `xor16_slices`).
2. If it cannot be mapped, STOP and request one of:
   - verbatim spec text for checksum section, or
   - reference implementation code, or
   - a captured frame sample (hex dump) with expected checksum bytes.
3. Extend the platform (NOT individual skills):
   - Add a new **generic** checksum implementation to `dvk/checksums.py` (parameterized if possible).
   - Update `spec/schemas/protocol.schema.json` to allow the new `checksum.type` and its `params` shape.
4. Generate `protocol.json` using only schema-supported types and params.

### Hard rule: no reverse modification of existing skills
If `protocol_spec_skill` discovers a checksum that is not supported by the current schema/runtime:
- Do NOT “patch” `transport_session.py`, `dvk_detect_protocol.py`, `dvk_decode.py`, etc. with protocol-specific logic.
- Only extend `dvk/checksums.py` + `spec/schemas/protocol.schema.json` (platform layer) after collecting required info from user.

## Outputs
| Output | Path |
|--------|------|
| `protocol.json` | `spec/protocols/{protocol_id}/protocol.json` |
| `commands.yaml` | `spec/command_sets/{command_set_id}/commands.yaml` |
| (Optional) model file | `spec/models/{model_id}.yaml` |
| (Optional) model bindings | `spec/models/{model_id}.yaml` (`protocol_bundles`) |

## Steps (must follow)
1. Confirm `protocol_id`, `protocol_version`, `command_set_id`, `command_set_version`, and doc source
2. List missing critical items and request from user (do not guess)
3. If onboarding a new model: request transport info and record it in `spec/models/{model_id}.yaml`
4. Generate `protocol.json` following `spec/schemas/protocol.schema.json`
5. Generate `commands.yaml` following `spec/schemas/commands.schema.json`
6. Self-check: assets must be sufficient for framing + decode/encode

## Rules
| Rule | Why |
|------|-----|
| Ask instead of guessing | offsets/length/checksum/endian must be correct |
| Bytes vs semantics separation | `protocol.json` is bytes-only; semantics belong in `commands.yaml` |
| Downstream compatibility | assets must support framing + decode/encode |
