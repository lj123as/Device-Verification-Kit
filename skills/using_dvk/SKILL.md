---
name: using_dvk
description: DVK entrypoint skill. This skill orchestrates the end-to-end pipeline (protocol → capture → decode/encode → analysis → report). Use when starting any DVK verification workflow.
---

# using_dvk (DVK Entry)

## Purpose
`using_dvk` is the single entrypoint for DVK. It validates inputs and orchestrates the end-to-end pipeline:
Protocol assets → Capture & framing → Decode/Encode → Analysis → Report.

## Reality check (important)
DVK is designed to be **low-touch** for real device testing:
- Default private workspace: `%USERPROFILE%\\DVK_Workspaces\\Device-Verification-Kit\\`
- Default private spec root: `%USERPROFILE%\\DVK_Workspaces\\Device-Verification-Kit\\_assets\\spec\\`
- When `model_id` is known and maps to a single protocol bundle, DVK should not ask you to manually locate protocol/commands files.

If you see many manual steps, treat it as a bug in the entry workflow: run `dvk_doctor.py` and fix the entrypoints.

## Environment checks (must do before real device tests)
Run the doctor once per machine/venv (no installs performed):

| Goal | Command |
|---|---|
| Offline pipeline readiness | `python tools/dvk_doctor.py --device-id <device_serial> --model-id <model_id> --port COM22 --mode offline` |
| Live + notebook readiness | `python tools/dvk_doctor.py --device-id <device_serial> --model-id <model_id> --port COM22 --mode live` |
| Live + MCP automation readiness | `python tools/dvk_doctor.py --device-id <device_serial> --model-id <model_id> --port COM22 --mode live-mcp` |

Notes:
- If you want to use a project venv, activate it first; the `python` you run decides everything.
- `nbclassic` is only required for notebook MCP automation; real-time viewing works in JupyterLab.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|-------|
| `device_serial` | Yes | Physical unit ID for this run (also used for folder names) |
| `model_id` | Preferred | Enables default baudrate + protocol bundle selection from model spec |
| Protocol bundle | Preferred | `{protocol_id + command_set_id}` recorded versions; auto-select if model maps to 1 bundle |
| Data source | Yes | Live device (UART/Network) or existing raw stream/frames file |
| Desired outputs | Yes | Decode only / Analysis / Report / Live |

## Protocol selection policy
| Situation | What to do |
|----------|------------|
| New model onboarding | Require explicit {protocol + commands} bundle; then write/extend model spec under private spec root |
| `model_id` maps to 1 protocol | Select directly (no detection) |
| `model_id` maps to N>1 protocols | Run `protocol_detection_skill` to propose candidates, then confirm once |

## One-command live testing (recommended)
Real-time validation (UART → decode → SharedMemory → live notebook):

`python tools/dvk_autolive.py --doctor --device-id <device_serial> --model-id <model_id> --start-publisher --port COM22 --ui lab`

Notes:
- Auto-selects protocol/commands/baudrate from the model spec when possible.
- Use `--python <path>` if you need to force a specific interpreter/venv.

## Offline workflow (must follow)
1. Run `dvk_doctor.py` once (environment + paths)
2. Capture/framing via `transport_session_skill`
3. Decode via `protocol_decode_skill`
4. (Optional) Run `analysis_skill`
5. (Optional) Run `report_skill`

## Rules
| Rule | Why |
|------|-----|
| Schema-driven only | Do not hardcode protocol parsing rules |
| Ask instead of guessing | Offsets/length/checksum/endianness must be correct |

