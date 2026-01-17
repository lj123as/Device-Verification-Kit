---
name: anomaly_detection_skill
description: This skill detects anomalies in DVK time series/telemetry (rule-based or statistical) and produces an anomaly list with evidence. Requires anomaly definitions, thresholds, and target columns; request missing inputs before detection.
---

# anomaly_detection_skill

## Purpose
Generate an anomaly list (with timestamps/indices and evidence) to support debugging and reporting.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines default paths |
| Dataset | Yes | prefer `cleaned.parquet` |
| Anomaly definition | Yes | thresholds / rules / statistical method |
| Columns | Yes | which signals to monitor |

## Outputs
| Artifact | Path |
|----------|------|
| Anomaly list | `reports/{device_id}/analysis/anomalies.csv` |
| Notebook | `reports/{device_id}/analysis/notebooks/anomaly.ipynb` |
| Evidence figures | `reports/{device_id}/analysis/figures/` |

## Workflow (recommended)
| Step | Action |
|------|--------|
| 1 | Confirm anomaly definition + acceptable false positives |
| 2 | Initialize notebook template: `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template anomaly` |
| 3 | Export `anomalies.csv` and link evidence in summary |

