---
name: data_cleaning_skill
description: This skill cleans DVK decoded datasets (missing values, outliers, dedup, time alignment) and persists a reproducible cleaned dataset. Requires cleaning rules and thresholds; request missing inputs before cleaning.
---

# data_cleaning_skill

## Purpose
Produce a reproducible `cleaned.parquet` dataset and a short record of cleaning rules applied.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines default paths |
| Input dataset | Yes | prefer `decoded.parquet` |
| Cleaning rules | Yes | drop/fill strategy, outlier policy |
| Thresholds | Optional | IQR/z-score windows, bounds |

## Outputs
| Artifact | Path |
|----------|------|
| Cleaned dataset | `data/processed/{device_id}/cleaned.parquet` |
| Cleaning notes | `data/processed/{device_id}/cleaning_notes.md` |
| Notebook | `reports/{device_id}/analysis/notebooks/cleaning.ipynb` |

## Workflow (recommended)
| Step | Action |
|------|--------|
| 1 | Confirm cleaning rules and thresholds (do not guess) |
| 2 | Initialize notebook template: `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template cleaning` |
| 3 | Run/iterate in Jupyter and write `cleaned.parquet` |
| 4 | Persist cleaning rules to `cleaning_notes.md` |

