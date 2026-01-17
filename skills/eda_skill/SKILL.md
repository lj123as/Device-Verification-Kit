---
name: eda_skill
description: This skill performs Exploratory Data Analysis on DVK decoded datasets to profile data quality, distributions, and relationships. Requires target columns and optional grouping keys; request missing inputs before analysis.
---

# eda_skill

## Purpose
Run a consistent EDA workflow on `data/processed/{device_id}/decoded.*` and produce evidence for reporting.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines default paths |
| Input dataset | Yes | prefer `decoded.parquet` |
| Target columns | Yes | key metrics to analyze |
| Grouping keys | Optional | mode, temp, config, etc. |

## Outputs
| Artifact | Path |
|----------|------|
| Notebook | `reports/{device_id}/analysis/notebooks/eda.ipynb` |
| Figures | `reports/{device_id}/analysis/figures/` |
| Summary | `reports/{device_id}/analysis/summary.md` |

## Workflow (recommended)
| Step | Action |
|------|--------|
| 1 | Ensure decoded dataset exists (`data/processed/{device_id}/decoded.*`) |
| 2 | Initialize notebook template: `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template eda` |
| 3 | Launch Jupyter: `python skills/analysis_skill/scripts/dvk_analysis.py launch --device-id <id>` |
| 4 | Complete EDA cells and save figures + summary |

## Environment (DVK does not bundle Python/Jupyter)
| What DVK provides | What user installs |
|------------------|--------------------|
| templates + scripts | Python + pip + Jupyter + libs |

Install deps:
- `pip install -r skills/analysis_skill/requirements.txt`

## References
| File | Purpose |
|------|---------|
| `skills/analysis_skill/references/eda_checklist.md` | EDA checklist used by this skill |

