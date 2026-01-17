---
name: report_skill
description: This skill produces deliverable reports (Markdown/HTML) from decoded/analysis outputs and evidence. Requires report audience, format, evidence sources, and metadata; request missing inputs before generating.
---

# report_skill

## Purpose
Create a consistent, reviewable report artifact from evidence + metadata.

## Required Inputs (ask if missing)
| Item | Required | Notes |
|------|----------|------|
| `device_serial` | Yes | determines default evidence paths (CLI flag is `--device-id`) |
| Audience/goal | Yes | internal dev / review / customer delivery |
| Format | Yes | `md` / `html` / `both` |
| Evidence sources | Yes | `data/processed/{device_serial}/` and (optional) `reports/**/analysis/` |
| Protocol reference | Recommended | pass `--protocol spec/protocols/<protocol_id>/protocol.json` for traceability |
| Required metadata | Yes | model, FW version, test conditions, sample size |

## Outputs (on disk)
| Output | Path |
|--------|------|
| Report artifact(s) | `reports/{device_serial}/` (default) or `--out-dir <path>` |

## Report tool
| Task | Command |
|------|---------|
| Generate Markdown | `python skills/report_skill/scripts/dvk_report.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --format md` |
| Generate HTML | `python skills/report_skill/scripts/dvk_report.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --format html` |
| Generate both | `python skills/report_skill/scripts/dvk_report.py --device-id SN-001 --protocol spec/protocols/<protocol_id>/protocol.json --format both` |
| With metadata | `python skills/report_skill/scripts/dvk_report.py --device-id SN-001 --model \"Model-X\" --fw-version \"1.0.0\" --tester \"QA\" --audience \"internal\"` |
| Custom output dir | `python skills/report_skill/scripts/dvk_report.py --device-id SN-001 --out-dir reports/<run_id>/SN-001 --format md` |

## Steps (must follow)
1. Confirm report format and audience
2. Request missing metadata/evidence (do not guess)
3. Generate report sections: Overview → Method → Results → Conclusions → Appendix
