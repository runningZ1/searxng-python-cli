# Project map

At most 120 lines. Execution rules live here.

## Repository

| Path | Role | Port | Boundary |
|---|---|---|---|
| `searxng_python_cli/` | Public command line | none | Editable |
| `scripts/searxng_cli.py` | Engine worker | none | Editable; do not start a web server |
| `scripts/settings.yml` | Local SearXNG settings | none | Editable |
| `config/profiles.json` | Web, image, and video profiles | none | Editable |
| `skills/searxng-python-cli/` | Agent skill | none | Keep examples aligned with the CLI |
| `docs/` | Private working notes | none | Gitignored. Not part of the public repository |
| `venv/`, `results/`, `cache/`, `data/`, `temp/`, `pip-cache/` | Local runtime | none | Gitignored. Stay inside the project |

Upstream engines come from https://github.com/searxng/searxng at commit `81371861f67226091d1c4df2e3908a11d3b54eb9`, installed as the `searxng` package. Do not vendor that tree. Do not start the interpreter from an upstream checkout. Project code and upstream code are AGPL-3.0-or-later.

## Commands

Working directory: repository root. Interpreter: `venv/Scripts/python.exe -I`.

| Task | Command |
|---|---|
| Version | `./venv/Scripts/python.exe -I -m searxng_python_cli version --output json` |
| Web search | `./venv/Scripts/python.exe -I -m searxng_python_cli search "query" --profile general --timeout 25` |
| Images | same command with `--profile fashion-images`, only when images were requested |
| Videos | same command with `--profile fashion-videos`, only when videos were requested |
| One engine | `./venv/Scripts/python.exe -I -m searxng_python_cli search "query" --engine sogou --timeout 25` |

## Rules

| Topic | Rule |
|---|---|
| Scope | Default to general web. Add images or videos only when asked. Use books, academic, code, or package engines only when the query matches |
| Failure | Report raw count, matched count, total time, and per-engine time. Keep failures, empty results, timeouts, captcha, and 429. Do not retry 429 or switch engines |
| Runtime | No other project's `.env`, no credentials in output, no mocks. Do not use `/tmp`, do not roll back git, do not change NTFS protections |
| Name | Repository and tool name: `searxng-python-cli` |

## Status

| Piece | State |
|---|---|
| Command line | Implemented. JSON envelope, limits, and exit codes |
| Image profile | Verified on 2026-11-12 before the upstream tree was removed from this directory: 159 raw, 26 matched, 22.437 seconds |
| Vendored `source/` | Removed. Upstream remains on GitHub. A separate newer checkout exists outside this repository and is not a byte-for-byte backup of the pinned commit |
