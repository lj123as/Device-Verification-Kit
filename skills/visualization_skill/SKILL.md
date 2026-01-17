---
name: visualization_skill
description: This skill creates visualizations for DVK datasets (time series plots, distributions, correlation, dashboards). Requires plot types, target columns, and output formats; request missing inputs before generating.
---

# visualization_skill

## Purpose
Produce consistent plots as evidence artifacts for reports and debugging.

## Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_id` | Yes | determines default paths |
| Dataset | Yes | decoded or cleaned |
| Plot list | Yes | plot types + columns |
| Format | Optional | png/svg/html |

## Outputs
| Artifact | Path |
|----------|------|
| Figures | `reports/{device_id}/analysis/figures/` |
| Notebook | `reports/{device_id}/analysis/notebooks/viz.ipynb` |

## Workflow (recommended)
| Step | Action |
|------|--------|
| 1 | Confirm plot list and formats |
| 2 | Initialize notebook template: `python skills/analysis_skill/scripts/dvk_analysis.py init --device-id <id> --template viz` |
| 3 | Generate figures and save under `figures/` |

