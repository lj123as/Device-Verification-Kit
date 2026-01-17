---
name: analysis_skill
description: This skill analyzes DVK structured data under data/processed using a Jupyter-first workflow. Includes environment checks and workspace initialization scripts; repo does not bundle Python/Jupyter. Requires analysis goals, metric definitions, and thresholds; confirm missing details before analysis.
---

# analysis_skill

## Purpose
Turn decoded data into evidence (plots/tables) and conclusions suitable for reporting, using a layered analysis pipeline.

## Default Engine
| Engine | Default | Notes |
|--------|---------|------|
| `JupyterEngine` | Yes | uses user-managed Python/Jupyter environment |
| `PlotlyEngine` | Optional | future extension |
| `DashboardEngine` | Optional | future extension |

## Sub-skills (standalone, but orchestrated here)
| Skill | When to use | Output focus |
|------|-------------|--------------|
| `eda_skill` | initial profiling and exploration | figures + notes |
| `data_cleaning_skill` | define and apply cleaning rules | `cleaned.parquet` |
| `metrics_skill` | compute KPIs and thresholds | `metrics.csv` |
| `anomaly_detection_skill` | find anomalies for debugging | `anomalies.csv` |
| `visualization_skill` | generate specific plots | figures |
| `live_analysis_skill` | real-time visualization + automation | SharedMemory + live notebook |

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines paths |
| Input data | Yes | files under `data/processed/{device_id}/` |
| Analysis goals | Yes | drift/linearity/noise/drop-rate/latency/custom |
| Metric definition | Yes | windows, filtering, thresholds, anomaly definition |

## Outputs
| Output | Path |
|--------|------|
| Charts + summary | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/reports/analysis/` (recommended) |
| Cleaned dataset | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/data/processed/cleaned.*` (recommended) |
| Notebook workspace | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/reports/analysis/notebooks/` |

## Data retention (default)
| Stage | Keep | Path |
|-------|------|------|
| Decoded input | Yes | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/data/processed/decoded.*` |
| Cleaned dataset | Recommended | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/data/processed/cleaned.parquet` |
| Intermediate scratch | Optional | `$DVK_WORKDIR/Device-Verification-Kit/{device_id}/runs/{run_id}/tmp/analysis/` |

## Steps (must follow)
1. Confirm input data and analysis goals
2. If metric definitions are unclear: request clarification before proceeding
3. Choose which sub-skill(s) to run (EDA / cleaning / metrics / anomaly / viz)
4. Generate the corresponding notebook template(s) via `dvk_analysis.py init --template ...`
5. Run in Jupyter and persist artifacts
6. Produce charts and a concise conclusion summary

## Pipeline Layers (recommended)
| Layer | Responsibility | Typical output |
|------|-----------------|----------------|
| Tool orchestration | env check, workspace init, launching engine | notebook workspace |
| Ingest & validation | load data, enforce dtypes, sanity checks | validation notes |
| Cleaning | missing/outliers/dedup/time alignment | `cleaned.*` |
| Analysis | EDA + metrics + anomaly detection | figures + tables |
| Packaging | summary markdown + links to evidence | `summary.md` |

## Environment (repo does not bundle Python/Jupyter)
| What you get in DVK | What you install |
|---------------------|------------------|
| scripts + requirements | Python + pip + jupyter + data libs |

### Install guidance (example)
| Step | Command |
|------|---------|
| Create venv | `python -m venv .venv` |
| Activate (Windows) | `.\\.venv\\Scripts\\activate` |
| Install deps | `pip install -r skills/analysis_skill/requirements.txt` |
| Check env | `python skills/analysis_skill/scripts/dvk_analysis.py check-env` |
| Init workspace (EDA) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template eda` |
| Init workspace (Cleaning) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template cleaning` |
| Init workspace (Metrics) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template metrics` |
| Init workspace (Anomaly) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template anomaly` |
| Init workspace (Viz) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template viz` |
| Init workspace (Full) | `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template full` |
| Launch jupyter | `python skills/analysis_skill/scripts/dvk_analysis.py launch --device-id <id> --mode lab` |

## References
| File | Purpose |
|------|---------|
| `skills/analysis_skill/references/eda_checklist.md` | consistent EDA flow |
| `skills/analysis_skill/references/upstream_skills.md` | upstream skill repos (reference only) |
