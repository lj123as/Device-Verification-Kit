# DVK (Device Verification Kit)

**Transform protocol documentation into complete device verification workflows—automatically.**

DVK eliminates the gap between device protocols and test infrastructure. Drop in your datasheet, capture data over UART, and get structured analysis notebooks—no custom parsing code required.

**The Pipeline**: Protocol → Capture → Decode → Analysis → Report

Built as an AI-native skill library with executable Python scripts. Works with Claude Code, Codex, and OpenCode.

---

## Features

- **Schema-driven protocol handling**: Define protocols in JSON, not code
- **Multi-transport support**: UART (primary), TCP, UDP, and offline file analysis
- **Flexible framing**: Dynamic/fixed length, multiple checksum types (sum8, CRC16, CRC32)
- **Modular skills**: Protocol spec → Transport session → Decode/Encode → Analysis → Report
- **Jupyter-first analysis**: Template-based notebooks for EDA, cleaning, metrics, anomaly detection
- **Multi-device workflows**: Track individual device instances with serial IDs
- **Protocol auto-detection**: Query/banner/sniff methods for multi-protocol models

---

## Installation

### For Claude Code

**Recommended (Marketplace)** - Install DVK from marketplace:

```text
/plugin marketplace add lj123as/embedded-marketplace
/plugin install dvk@embedded-marketplace
```

Marketplace installs are version-pinned; DVK releases should be tagged as `vX.Y.Z` (e.g., `v0.1.0`).

Maintainers: to host your own marketplace repo, see `docs/marketplace.md`.

**Dev / Local Checkout** - Clone this repo, then open the cloned folder in Claude Code:

```bash
cd <YOUR_CODE_DIR>
git clone https://github.com/lj123as/Device-Verification-Kit.git
cd Device-Verification-Kit
```

Example clone locations: `~/dev/Device-Verification-Kit`, `C:\dev\Device-Verification-Kit`.

Then in Claude Code:
```
Use using_dvk skill to get started
```

**Detailed setup**: [.claude-plugin/INSTALL.md](.claude-plugin/INSTALL.md)

### Optional: Embedded Memory plugin

DVK can optionally use the **embedded-memory** plugin for auditable, project-local knowledge capture (observations → rules → query/resolve).

- Repo: `https://github.com/lj123as/embedded-memory.git`
- Suggested integration: add as a git submodule at `tools/embedded-memory`
- Enable hooks: set `DVK_EMBEDDED_MEMORY=1`
- Optional subject hints: set `DVK_MODEL_ID` and `DVK_FW_VERSION` (otherwise defaults to `device_id` / `unknown`)
- When enabled, DVK emits `runs/<run_id>/observations.jsonl` during capture/decode/analysis/report and writes `runs/<run_id>/compile_request.json` after report generation.

### For Codex

Fetch and follow instructions from:
`https://raw.githubusercontent.com/lj123as/Device-Verification-Kit/main/.codex/INSTALL.md`

```bash
git clone https://github.com/lj123as/Device-Verification-Kit.git ~/.codex/dvk
# Run inside WSL2 / bash (dvk-codex is a bash script)
bash ~/.codex/dvk/.codex/dvk-codex bootstrap
```

Follow the bootstrap instructions to complete setup.

**Detailed setup**: [.codex/INSTALL.md](.codex/INSTALL.md)

### For OpenCode

Fetch and follow instructions from:
`https://raw.githubusercontent.com/lj123as/Device-Verification-Kit/main/.opencode/INSTALL.md`

```bash
git clone https://github.com/lj123as/Device-Verification-Kit.git ~/.config/opencode/dvk
ln -s ~/.config/opencode/dvk/.opencode/plugin.json ~/.config/opencode/plugins/dvk.json
```

Restart OpenCode, then use `find_skills dvk` to discover available skills.

**Detailed setup**: [.opencode/INSTALL.md](.opencode/INSTALL.md)

### Python Dependencies

DVK requires Python 3.9+ and several packages.

DVK is designed to run in a **single virtual environment** (`.venv/`, gitignored).

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install aggregated deps (recommended)
pip install -r requirements.txt

# Or install only the skills you need:
# pip install -r skills/transport_session_skill/requirements.txt
# pip install -r skills/protocol_decode_skill/requirements.txt
# pip install -r skills/analysis_skill/requirements.txt
```

---

## Quick Start Example

Verify a sensor device in 5 commands:

```bash
# 1. Capture 10 seconds of UART data
python skills/transport_session_skill/scripts/transport_session.py \
  capture-uart --device-id SN-001 --port COM5 --baudrate 115200 --duration-s 10

# 2. Frame the raw stream
python skills/transport_session_skill/scripts/transport_session.py \
  align --device-id SN-001 --protocol spec/protocols/example/protocol.json

# 3. Decode frames to structured data
python skills/protocol_decode_skill/scripts/dvk_decode.py \
  --device-id SN-001 --protocol spec/protocols/example/protocol.json --format csv

# 4. Generate analysis notebook
python skills/analysis_skill/scripts/dvk_analysis.py init --device-id SN-001 --template eda
python skills/analysis_skill/scripts/dvk_analysis.py launch --device-id SN-001

# 5. Create verification report
python skills/report_skill/scripts/dvk_report.py \
  --device-id SN-001 --format md --model Model-X --fw-version 1.0.0
```

**Result**: evidence-backed pass/fail metrics and exported artifacts under:
`$DVK_WORKDIR/Device-Verification-Kit/<device_id>/runs/<run_id>/reports/` (default: `~/DVK_Workspaces/Device-Verification-Kit/`).

---

## What's Inside

DVK provides 13 integrated skills organized by workflow stage:

### Protocol & Transport Layer

- **protocol_spec_skill** - Extract frame definitions from datasheets/PDFs → generate `protocol.json` + `commands.yaml`
- **transport_session_skill** - Capture bytes from UART/TCP/UDP and frame using protocol assets
- **protocol_detection_skill** - Auto-detect device protocol using query/banner/sniff methods

### Data Processing

- **protocol_decode_skill** - Decode framed bytes into structured datasets (CSV/JSON/Parquet)
- **protocol_encode_skill** - Encode business commands into protocol frames
- **data_cleaning_skill** - Handle gaps, duplicates, and quality issues

### Analysis & Metrics

- **analysis_skill** - Orchestrate Jupyter-based analysis workflows
- **eda_skill** - Generate exploratory data analysis notebooks
- **metrics_skill** - Compute verification KPIs (drift, noise, latency, custom metrics)
- **anomaly_detection_skill** - Statistical outlier detection
- **visualization_skill** - Generate charts and time-series plots

### Reporting

- **report_skill** - Generate deliverable reports (Markdown/HTML) with evidence

### Workflow Orchestration

- **using_dvk** - Entrypoint skill that guides you through the complete workflow

---

## Repository Structure

```
Device-Verification-Kit/
├── .claude-plugin/         # Claude Code plugin metadata
│   └── plugin.json         # Skill registry
├── skills/                 # DVK skills (each with SKILL.md + scripts/)
│   ├── using_dvk/          # Entrypoint skill
│   ├── protocol_spec_skill/        # Protocol onboarding
│   ├── transport_session_skill/    # Data capture & framing
│   ├── protocol_decode_skill/      # Frame decoding
│   ├── protocol_encode_skill/      # Command encoding
│   ├── protocol_detection_skill/   # Auto-detect protocol
│   ├── analysis_skill/             # Jupyter analysis orchestration
│   ├── report_skill/               # Report generation
│   └── [sub-skills: eda, data_cleaning, metrics, anomaly_detection, visualization]
├── spec/                   # Protocol assets & schemas
│   ├── protocols/{protocol_id}/protocol.json       # Frame definitions
│   ├── command_sets/{command_set_id}/commands.yaml # Command definitions
│   ├── models/{model_id}.yaml                      # Device model registry
│   └── schemas/            # JSON schemas for validation
├── data/                   # Runtime data (gitignored)
│   ├── raw/{device_serial}/        # Captured streams & frames
│   └── processed/{device_serial}/  # Decoded datasets
├── reports/                # Analysis outputs (gitignored)
└── runs/                   # Run records (gitignored)
```

## Runtime Workspace (default)

By default, runtime artifacts are written outside the repo to:
`$DVK_WORKDIR/Device-Verification-Kit/` (default: `~/DVK_Workspaces/Device-Verification-Kit/`).

Typical layout:
```
$DVK_WORKDIR/Device-Verification-Kit/
  _logs/                                  # launcher logs (publisher/jupyter)
  <device_id>/
    runs/<run_id>/
      data/raw/                            # captures / frames
      data/processed/                      # decoded datasets
      reports/                             # analysis outputs
      logs/                                # run logs
    live/notebooks/live_<ts>.ipynb         # live viewer notebook (generated)
```

## Private Protocol Assets (isolation)

This repo should only contain **demo/example** protocol assets under `spec/`.
For private devices, store protocol assets outside the repo and reference them by id:

- Set `DVK_SPEC_ROOT` to your private spec root (recommended).
- Or use the default private root:
  `$DVK_WORKDIR/Device-Verification-Kit/_assets/spec/`

Expected structure:
```
$DVK_SPEC_ROOT/
  protocols/<protocol_id>/protocol.json
  command_sets/<command_set_id>/commands.yaml
  models/<model_id>.yaml
```

`tools/dvk_autolive.py` and core scripts accept either:
- an explicit file path, or
- an id (e.g. `--protocol <protocol_id>` / `--commands <command_set_id>`)

---

## Protocol Definition

DVK uses two assets per protocol:

### 1. `protocol.json` (Framing & Decoding)
Defines byte-level frame structure:
```json
{
  "protocol_id": "example_device_protocol",
  "protocol_version": "0.1.0",
  "frames": [{
    "name": "TelemetryFrame",
    "header": ["0xAA", "0x55"],
    "length": {"mode": "dynamic", "field": {...}, "overhead_bytes": 5},
    "fields": [
      {"name": "msg_id", "offset": 2, "length": 1, "type": "uint8"},
      {"name": "temperature", "offset": 4, "length": 2, "type": "int16_le"}
    ],
    "checksum": {"type": "crc16", "range": [0, -2], "store_at": -2, ...}
  }]
}
```

### 2. `commands.yaml` (Business Semantics)
Defines human-friendly commands:
```yaml
command_set_id: example_device_protocol_cmds
command_set_version: "0.1.0"
commands:
  - name: get_temperature
    id: 0x10
    params:
      - {name: sensor_id, type: uint8, range: [0, 3], default: 0}
    response:
      - {name: temperature, type: int16_le, unit: "°C"}
```

**Schemas**: See `spec/schemas/protocol.schema.json` and `spec/schemas/commands.schema.json`

---

## Key Concepts

- **Device Serial vs Model**: `device_serial` identifies a physical unit; `model_id` maps to protocol bundles
- **Protocol Bundle**: `{protocol_id + command_set_id}` combo with version tracking
- **Transport Agnostic**: `protocol.json` defines framing only; transport binding is in `spec/models/{model_id}.yaml`
- **Session vs Frame**: Session captures raw stream; framing extracts protocol frames
- **Jupyter-first Analysis**: Templates generate notebooks, not hardcoded scripts

---

## Supported Checksum Types

| Type   | Parameters Required | Notes |
|--------|---------------------|-------|
| `sum8` | `store_at` | Simple 8-bit sum |
| `crc16` | `store_format`, `params` (poly/init/xorout/refin/refout) | Configurable CRC-16 variants |
| `crc32` | `store_format`, `params` (poly/init/xorout/refin/refout) | Configurable CRC-32 variants |

**CRC Parameter Example (CRC-32)**:
```json
{
  "checksum": {
    "type": "crc32",
    "range": [0, -4],
    "store_at": -4,
    "store_format": "uint32_le",
    "params": {
      "poly": 3988292384,      // 0xEDB88320 (reflected)
      "init": 4294967295,       // 0xFFFFFFFF
      "xorout": 4294967295,     // 0xFFFFFFFF
      "refin": true,
      "refout": true
    }
  }
}
```

---

## Multi-Device Testing

DVK supports testing multiple device units with the same protocol:

```bash
# Device instance SN-001
python .../transport_session.py capture-uart --device-id SN-001 --port COM5 ...
python .../dvk_decode.py --device-id SN-001 ...

# Device instance SN-002
python .../transport_session.py capture-uart --device-id SN-002 --port COM6 ...
python .../dvk_decode.py --device-id SN-002 ...
```

Data isolation:
- `$DVK_WORKDIR/Device-Verification-Kit/SN-001/runs/<run_id>/data/raw/` vs `$DVK_WORKDIR/Device-Verification-Kit/SN-002/runs/<run_id>/data/raw/`
- `$DVK_WORKDIR/Device-Verification-Kit/SN-001/runs/<run_id>/data/processed/` vs `$DVK_WORKDIR/Device-Verification-Kit/SN-002/runs/<run_id>/data/processed/`

---

## Claude Code Skills

DVK is designed as a **Claude Code skill library**. Each skill directory contains:
- `SKILL.md`: Skill metadata & usage guide
- `scripts/`: Executable Python tools
- `requirements.txt`: Python dependencies

**Using with Claude Code**:
```bash
# Invoke skills through Claude
claude: "Use using_dvk skill to verify device SN-001"
claude: "Run protocol_decode_skill to decode frames for SN-001"
```

Skills are registered in `.claude-plugin/plugin.json`.

---

## Examples

See `spec/protocols/example_device_protocol/` for a complete example protocol with:
- Dynamic length framing
- CRC-16 checksum
- Multi-field telemetry frames
- Command/response definitions

---

## Development

**Repo does NOT bundle**:
- Python interpreter
- Jupyter Lab/Notebook
- Data science libraries (pandas, numpy, matplotlib, etc.)

**You install**:
```bash
# Analysis dependencies
pip install -r skills/analysis_skill/requirements.txt

# Protocol detection dependencies (optional)
pip install -r skills/protocol_detection_skill/requirements.txt
```

**Environment check**:
```bash
python skills/analysis_skill/scripts/dvk_analysis.py check-env
```

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

[MIT License](LICENSE)

---

## Using DVK with AI Assistants

DVK is designed as an **AI-native skill library**. AI assistants automatically invoke skills based on context:

### Claude Code Example

```text
User: "I need to verify sensor device SN-001 connected to COM5"
Claude: [Automatically invokes using_dvk skill]
        "I'll guide you through the complete DVK workflow..."
```

### Skill Invocation Patterns

**Automatic (Recommended)**: AI detects task and invokes appropriate skill

```text
"Decode the frames for SN-001"
→ AI invokes protocol_decode_skill automatically
```

**Explicit**: Directly request a specific skill

```text
Use protocol_spec_skill to onboard the temperature sensor protocol
Use analysis_skill to generate EDA notebook for SN-001
```

### Available Skills

All 13 skills are documented in their respective `SKILL.md` files:

- [skills/using_dvk/SKILL.md](skills/using_dvk/SKILL.md) - Start here
- [skills/protocol_spec_skill/SKILL.md](skills/protocol_spec_skill/SKILL.md)
- [skills/transport_session_skill/SKILL.md](skills/transport_session_skill/SKILL.md)
- [See full list in .claude-plugin/plugin.json](.claude-plugin/plugin.json)

---

## Platform-Specific Documentation

- **Claude Code**: [.claude-plugin/INSTALL.md](.claude-plugin/INSTALL.md)
- **Codex**: [.codex/INSTALL.md](.codex/INSTALL.md)
- **OpenCode**: [.opencode/INSTALL.md](.opencode/INSTALL.md)

---

## How to Contribute

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:

- Skill development standards
- Protocol asset schemas
- Testing requirements
- Commit message format

---

## Support

- **Issues**: [GitHub Issues](https://github.com/lj123as/Device-Verification-Kit/issues)
- **Discussions**: [GitHub Discussions](https://github.com/lj123as/Device-Verification-Kit/discussions)
- **Documentation**: This README and skill-specific `SKILL.md` files

---

**Built with**: Python 3.9+, PySerial, PyYAML, pandas, Jupyter

**Designed for**: Claude Code, Codex, OpenCode, and standalone CLI usage
