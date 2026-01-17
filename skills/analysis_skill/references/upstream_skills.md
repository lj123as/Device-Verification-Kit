# Upstream Skills (References Only)

These repositories are used as inspiration and reference. DVK does **not** include them as git submodules by default.

## Candidates
| Repo | Why it’s useful |
|------|------------------|
| https://github.com/K-Dense-AI/claude-scientific-skills/tree/main/scientific-skills/exploratory-data-analysis | EDA workflow patterns and checklists |
| https://github.com/Dexploarer/claudius-skills/tree/0fe8bc3f719b1179694bf6d21ecfcf6a7bd7f746/examples/intermediate/data-science-skills | Jupyter-oriented data science skill patterns |

## Why not submodule (default)
| Reason | Notes |
|--------|------|
| Contract mismatch | DVK uses `data/processed/{device_id}` + `reports/{device_id}` conventions |
| Upgrade friction | submodules complicate updates and reviews |
| Style consistency | DVK requires English + table-first SKILL.md |

If you want a submodule workflow, decide:
1) pinned commit policy, 2) update cadence, 3) how DVK patches local wrappers around upstream skills.

