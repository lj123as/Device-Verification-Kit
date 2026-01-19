# Installing DVK for Codex

## IMMEDIATELY RUN THIS BOOTSTRAP COMMAND

```bash
# Run inside WSL2 / bash (dvk-codex is a bash script)
bash ~/.codex/dvk/.codex/dvk-codex bootstrap
```

After running the bootstrap, **follow the displayed instructions carefully.**

---

## Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/lj123as/Device-Verification-Kit.git ~/.codex/dvk
```

### 2. Configure Codex

Add DVK skills to your `~/.codex/AGENTS.md`:

```markdown
# DVK (Device Verification Kit)

**IMPORTANT: Before using DVK, run the bootstrap command:**

```bash
bash ~/.codex/dvk/.codex/dvk-codex bootstrap
```

This will:
- Display available DVK skills
- Check your Python environment
- Provide next steps for skill activation

## Available Skills

DVK provides protocol-driven device verification:

- Protocol onboarding from documentation
- Multi-transport data capture (UART/TCP/UDP)
- Frame decoding and command encoding
- Jupyter-based analysis workflows
- Automated report generation

Skills are prefixed with `dvk:` in Codex.
```

### 3. Python Environment Setup

DVK requires Python 3.9+ and dependencies:

```bash
cd ~/.codex/dvk

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r skills/transport_session_skill/requirements.txt
pip install -r skills/protocol_decode_skill/requirements.txt
pip install -r skills/analysis_skill/requirements.txt
```

---

## Verification

Run the bootstrap command to verify installation:

```bash
bash ~/.codex/dvk/.codex/dvk-codex bootstrap
```

Expected output:
- List of 13 available DVK skills
- Python environment status
- Example usage patterns

---

## Updating

```bash
cd ~/.codex/dvk
git pull origin main
pip install -r skills/analysis_skill/requirements.txt --upgrade
```
