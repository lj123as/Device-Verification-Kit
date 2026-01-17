---
name: live_analysis_skill
description: Automates real-time DVK visualization and analysis from DVK SharedMemory streams. Launches a browser notebook UI, opens live.ipynb, and (after a one-time bridge cell) enables MCP-driven notebook execution and artifact export. MCP automation requires nbclassic.
---

# live_analysis_skill

## Purpose
Provide an **automated** real-time analysis loop for DVK:
- Consume point rows from a DVK SharedMemory ring buffer (fixed capacity; no CSV for realtime)
- Render a live 2D point cloud and derived metrics in a notebook
- Enable **MCP automation** (run cells / export figures) after a one-time bridge cell

## Scope boundary
| Concern | Owned by | Notes |
|---|---|---|
| Device connection / UART capture | `transport_session_skill` | Produces framed/decoded streams and/or live publisher |
| Frame decode + semantics | `protocol_decode_skill` + `commands.yaml` | Produces semantic point rows |
| Live publishing (SharedMemory) | `dvk_live.py` | Bridge from decode to visualization |
| Live visualization + automation | `live_analysis_skill` | This skill |

## What is automated vs manual
| Step | Automated | Manual | Notes |
|---|---:|---:|---|
| Ensure a SharedMemory publisher exists (`dvk.<device_id>`) | Optional | Depends | Publisher is upstream; this skill can start it as a convenience |
| Start notebook UI server | Yes | No | Uses user Python environment |
| Open `live.ipynb` in browser | Yes | No | Uses token URL (no login page) |
| Enable MCP control inside notebook | Partial | **Once per session** | Run the `JupyterNotebook MCP bridge` cell once |
| Run all cells / re-run live plot / export artifacts | Yes (via MCP) | No | After bridge is ready |

## Inputs (ask if missing)
| Item | Required | Example | Notes |
|---|---:|---|---|
| `device_id` | Yes | `22` | Also used for SharedMemory name `dvk.<device_id>` |
| SharedMemory name | Optional | `dvk.22` | Defaults to `dvk.<device_id>` |
| Publisher config | Optional | UART params + protocol/commands paths | Only needed if using the convenience launcher to start publisher |

## Outputs
| Artifact | Path / Name |
|---|---|
| SharedMemory ring | `dvk.<device_id>` (`.ctrl` + `.data`) |
| Live notebook | `$DVK_WORKDIR/Device-Verification-Kit/<device_id>/live/notebooks/live.ipynb` |
| Figures (recommended) | `$DVK_WORKDIR/Device-Verification-Kit/<device_id>/runs/<run_id>/reports/analysis/figures/` |

## Entry point (one command)
| Goal | Command |
|---|---|
| Launch notebook UI + open live notebook | `python tools/dvk_autolive.py --device-id <id>` |
| Launch + start publisher (convenience) | `python tools/dvk_autolive.py --device-id <id> --start-publisher --port COMx --baudrate <baud> --protocol <path> [--commands <path>]` |

### UI selection (important)
`jupyter-notebook-mcp` injects a JavaScript client that uses the classic Notebook API (`Jupyter.notebook`).
That API is available in **nbclassic**, not in JupyterLab/Notebook 7 UI.

| UI | Works for live plotting | Works for MCP automation |
|---|---:|---:|
| JupyterLab (`/lab`) | Yes | No (by default) |
| nbclassic (`/tree`) | Yes | Yes |

Install nbclassic (user environment):
| Step | Command |
|---|---|
| Install | `pip install nbclassic` |

Run with nbclassic explicitly:
| Goal | Command |
|---|---|
| Force nbclassic UI | `python tools/dvk_autolive.py --device-id <id> --port COMx --baudrate <baud> --ui nbclassic` |

### Default flags (public-safe)
| Flag | Meaning |
|---|---|
| `--protocol` | protocol asset path (your environment) |
| `--commands` | command-set asset path (your environment) |
| `--notebook` | output notebook path template |

## MCP automation notes (critical)
| Topic | Requirement |
|---|---|
| MCP server | `jupyter-notebook-mcp` must be installed and enabled in Codex MCP config |
| Notebook bridge | The notebook must run the `JupyterNotebook MCP bridge` cell **once per session** |
| After bridge | Codex can call tools like `JupyterNotebook.run_all_cells`, `run_cell`, `get_image_output` |

## Troubleshooting
| Symptom | Likely cause | Fix |
|---|---|---|
| Browser opens login page asking token | Opened `/lab` without token | Use the `dvk_autolive.py` printed `notebook:` URL |
| Publisher fails to start | COM port busy | Close serial monitor tools; retry |
| Live plot looks static | Notebook backend not refreshing | Prefer JupyterLab browser; ensure the plot cell updates `seq=` |
| Bridge cell import fails | Kernel can't import `jupyter_ws_server` | Set `JUPYTER_MCP_SRC` to `.../jupyter-notebook-mcp/src` and restart notebook server |
| MCP tools `ping` but cannot run cells | Notebook UI is JupyterLab | Use `--ui nbclassic` and re-run the bridge cell |

## References
| File | Purpose |
|---|---|
| `tools/dvk_autolive.py` | One-command launcher |
| `skills/transport_session_skill/scripts/dvk_live.py` | UART -> frame -> semantics -> SharedMemory |
| `dvk/shm.py` | SharedMemory ring buffer |
| `skills/live_analysis_skill/scripts/dvk_live_analysis.py` | Live notebook generator (workdir output) |
