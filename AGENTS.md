# Repository Guidelines

This repository contains **DVK (Device Verification Kit)**: Python scripts and “skills” that turn protocol specs + captured device data into decoded datasets, analysis notebooks, and reports.

## Project Structure

- `dvk/`: Core Python utilities (workdir management, checksums, semantics).
- `skills/`: Workflow stages implemented as skills.
  - `skills/<skill_name>/SKILL.md`: User/agent-facing instructions with YAML frontmatter.
  - `skills/<skill_name>/scripts/`: Executable CLIs (generally run via `python ...`).
  - Optional: `requirements.txt`, `references/`, `assets/`.
- `spec/`: Protocol assets and JSON schemas (e.g., `spec/schemas/` and example `spec/protocols/...`).
- `docs/`: Project documentation (including marketplace notes).
- `.claude-plugin/`, `.codex/`, `.opencode/`: Integration metadata for different agent runtimes.
- `tools/`: Optional tooling and integrations (may include submodules).

## Setup, Build, and Run

DVK is designed for a single local virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Common entrypoints:
- Environment check: `python skills/analysis_skill/scripts/dvk_analysis.py check-env`
- Capture/alignment/decoding/reporting: see examples in `README.md` (all scripts support `--help`).

## Coding Style & Naming

- Python: 4-space indentation, PEP 8, clear error messages, argparse CLIs.
- Naming: `snake_case.py` files, `snake_case` functions/vars, `PascalCase` classes.
- Skills: keep changes scoped to a single skill when possible; mirror existing `SKILL.md` structure and place new CLIs under `skills/<skill>/scripts/`.
- Protocol assets: follow `spec/schemas/*.json` and use descriptive IDs (e.g., `protocol_id: device_model_protocol`).

## Testing Guidelines

There is no centralized automated test suite in this repo today. Before opening a PR:
- Run basic sanity checks: `python -m compileall dvk skills`
- Smoke test the touched CLI(s): `python skills/<skill>/scripts/<tool>.py --help`
- If you changed decoding/analysis/reporting, run an end-to-end workflow against an example protocol in `spec/`.

## Commits & Pull Requests

- Commit subjects are typically imperative and concise (e.g., “Add optional embedded-memory integration”); use optional scope prefixes like `DVK:` when helpful.
- PRs should include: what changed, why, how to test, and any updated schemas/docs (`README.md`, `SKILL.md`, `spec/`).
- Avoid committing captured device data; outputs should live under `$DVK_WORKDIR` (see `README.md`).
