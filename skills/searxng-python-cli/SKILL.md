---
name: searxng-python-cli
description: Search the web, images, or videos through the searxng-python-cli tool. Use when the user wants SearXNG engine results without starting the SearXNG website. Do not use for the SearXNG web app, Valkey, or Docker.
metadata:
  tested-cli-version: "0.1.0"
---

# searxng-python-cli

Use `python -m searxng_python_cli` or `searxng-python-cli` to call upstream SearXNG engines. Prefer `--output json`.

## Prerequisites

```bash
python -m searxng_python_cli version --output json
python -m searxng_python_cli agent doctor --engines wikipedia --output json
```

Install from the repository with `pip install -r requirements.txt` and `pip install -e .` when the module is missing. Upstream is https://github.com/searxng/searxng at commit `81371861f67226091d1c4df2e3908a11d3b54eb9`.

## Operating rules

- Start with `agent schema --output json` when a flag is unknown.
- Default search is not image or video. Use `--profile fashion-images` or `--profile fashion-videos` only when the user asked for that type.
- Keep `--limit` at 20 unless more rows are required. `--limit 0` removes the cap. The maximum other value is 200.
- Do not retry when `error.retryable` is false. 429, captcha, and timeout use exit 4 and are not retried.
- Do not switch engines after a failure.
- Results include thumbnail URLs. They are not downloaded image files.
- One successful count is not a permanent engine inventory.

## Commands

| Goal | Command | Effect | Returns |
| --- | --- | --- | --- |
| Version | `searxng-python-cli version --output json` | Read-only | version and upstream commit |
| Engine sample | `searxng-python-cli engines list --limit 20 --output json` | Read-only | applied limit, total_count, engines |
| Profiles | `searxng-python-cli profiles list --output json` | Read-only | groups and profiles |
| Web search | `searxng-python-cli search "query" --profile general --limit 20 --output json` | Network read, not idempotent | counts, limited results |
| Image search | `searxng-python-cli search "query" --profile fashion-images --limit 20 --output json` | Network read | image records and thumbnail URLs |
| One engine | `searxng-python-cli search "query" --engine wikipedia --timeout 25 --output json` | Network read | that engine only |

## Error decisions

| Exit | Response |
| --- | --- |
| 2 | Fix arguments. Read `error.message` or `--help` |
| 3 | Install the `searxng` package or restore `config/profiles.json` |
| 4 | Stop. Do not retry 429, captcha, or timeout |
| 1 | Stop and inspect `engines` in the report. Do not loop |
| 0 | Continue. Empty `count` is a real empty result, not a crash |

## Known limitations

- Category `images` currently selects 51 engines. The command refuses more than 12 unless `--allow-large` is set.
- Wikipedia search for `searxng` returned `count: 0` with exit 0 on 2026-11-12 after the vendored tree was removed. That verifies the call path, not that every engine has hits.
- Web UI, HTTP API, Valkey, Docker, bangs, autocomplete, and image download are out of scope.
- Last verified with `searxng-python-cli` 0.1.0 on Windows, Python 3.12.
