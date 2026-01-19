# Installing DVK for Claude Code

## Quick Installation

### Marketplace install (recommended)

Install DVK from your team marketplace:

```text
/plugin marketplace add lj123as/embedded-marketplace
/plugin install dvk@embedded-marketplace
```

Marketplace installs are version-pinned; DVK releases should be tagged as `vX.Y.Z` (e.g., `v0.1.0`).

Maintainers: to host your own marketplace repo, see `docs/marketplace.md`.

### Dev / local checkout

Clone this repo into your normal “code/projects” directory (or download a zip), then open the cloned folder in Claude Code:

```bash
cd <YOUR_CODE_DIR>
git clone https://github.com/lj123as/Device-Verification-Kit.git
cd Device-Verification-Kit
```

## Verification

Open Claude Code in this repository and try:

```
Use using_dvk skill to get started
```

You should see DVK's entrypoint skill activate with workflow guidance.

---

## Available Skills

DVK provides 13 integrated skills:

### Protocol & Transport
- `using_dvk` - Workflow entrypoint and orchestration
- `protocol_spec_skill` - Protocol onboarding from documentation
- `transport_session_skill` - Data capture and framing
- `protocol_detection_skill` - Auto-detect device protocols

### Data Processing
- `protocol_decode_skill` - Frame decoding to structured data
- `protocol_encode_skill` - Command encoding
- `data_cleaning_skill` - Data quality assurance

### Analysis
- `analysis_skill` - Jupyter analysis orchestration
- `eda_skill` - Exploratory data analysis
- `metrics_skill` - KPI computation
- `anomaly_detection_skill` - Outlier detection
- `visualization_skill` - Chart generation

### Reporting
- `report_skill` - Deliverable report generation

---

## Python Environment Setup

DVK requires Python 3.9+ and several packages:

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies for skills you'll use
pip install -r skills/transport_session_skill/requirements.txt
pip install -r skills/protocol_decode_skill/requirements.txt
pip install -r skills/analysis_skill/requirements.txt
```

**Verify installation:**
```bash
python skills/analysis_skill/scripts/dvk_analysis.py check-env
```

---

## Usage Pattern

DVK skills work through Claude Code's skill invocation:

```
# Workflow orchestration
Use using_dvk to capture and decode data from device SN-001

# Direct skill invocation
Use protocol_decode_skill to decode frames for SN-001
Use analysis_skill to generate EDA notebook for SN-001
Use report_skill to create verification report for SN-001
```

---

## Updating

Pull latest changes from the repository:

```bash
git pull origin main
```

If new dependencies were added, reinstall requirements:

```bash
pip install -r skills/[skill_name]/requirements.txt --upgrade
```
