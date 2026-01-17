# Installing DVK for OpenCode

## Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/lj123as/Device-Verification-Kit.git ~/.config/opencode/dvk
```

### 2. Create Symlink

Link DVK's OpenCode plugin file to OpenCode's plugin directory:

```bash
ln -s ~/.config/opencode/dvk/.opencode/plugin.json ~/.config/opencode/plugins/dvk.json
```

### 3. Restart OpenCode

Reload OpenCode to activate the DVK plugin.

---

## Usage Pattern

DVK operates through OpenCode's skill system with three lookup tiers:

1. **Project-level skills** (highest priority, prefixed with `project:`)
2. **Personal skills** in `~/.config/opencode/skills/`
3. **DVK skills** (prefixed with `dvk:`)

### Skill Discovery

```
find_skills dvk
```

### Skill Invocation

```
use_skill dvk:using_dvk
use_skill dvk:protocol_decode_skill
use_skill dvk:analysis_skill
```

---

## Python Environment Setup

DVK requires Python 3.9+ and dependencies:

```bash
cd ~/.config/opencode/dvk

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r skills/transport_session_skill/requirements.txt
pip install -r skills/protocol_decode_skill/requirements.txt
pip install -r skills/analysis_skill/requirements.txt
```

**Verify installation:**
```bash
python skills/analysis_skill/scripts/dvk_analysis.py check-env
```

---

## Available Skills

DVK provides 13 skills organized by workflow stage:

**Protocol & Transport:**
- `using_dvk` - Workflow orchestration
- `protocol_spec_skill` - Protocol onboarding
- `transport_session_skill` - Data capture
- `protocol_detection_skill` - Auto-detection

**Data Processing:**
- `protocol_decode_skill` - Frame decoding
- `protocol_encode_skill` - Command encoding
- `data_cleaning_skill` - Data quality

**Analysis:**
- `analysis_skill` - Jupyter orchestration
- `eda_skill` - Exploratory analysis
- `metrics_skill` - KPI computation
- `anomaly_detection_skill` - Outlier detection
- `visualization_skill` - Chart generation

**Reporting:**
- `report_skill` - Report generation

---

## Updating

```bash
cd ~/.config/opencode/dvk
git pull origin main
```

If new dependencies were added:

```bash
source .venv/bin/activate
pip install -r skills/[skill_name]/requirements.txt --upgrade
```
