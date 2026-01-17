---
name: metrics_skill
description: This skill computes DVK verification metrics (summary stats, drift, noise, drop-rate, latency, custom KPIs) from decoded/cleaned data. Requires metric definitions, windows, and pass/fail thresholds; request missing inputs before computing.
---

# metrics_skill

## Purpose
Turn datasets into explicit metrics with definitions and thresholds suitable for reporting and automation.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines default paths |
| Dataset | Yes | prefer `cleaned.parquet` if available |
| Metric definitions | Yes | formulas, windows, units |
| Thresholds | Yes | pass/fail criteria |

## Outputs
| Artifact | Path |
|----------|------|
| Metrics table | `reports/{device_id}/analysis/metrics.csv` |
| Metrics definition | `reports/{device_id}/analysis/metrics_definition.md` |
| Notebook | `reports/{device_id}/analysis/notebooks/metrics.ipynb` |

## Workflow (recommended)
| Step | Action |
|------|--------|
| 1 | Confirm metric definitions + thresholds (do not guess) |
| 2 | Initialize notebook template: `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template metrics` |
| 3 | Compute metrics and export CSV + definitions |

