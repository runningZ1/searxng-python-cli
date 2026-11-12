# searxng-python-cli

Headless Python command line for [SearXNG](https://github.com/searxng/searxng) engines. It does not start the SearXNG web application, Docker, or Valkey.

The engine implementation is upstream SearXNG, pinned in `requirements.txt` at commit `81371861f67226091d1c4df2e3908a11d3b54eb9`. This repository does not vendor that source tree. License: AGPL-3.0-or-later.

## Install

Python 3.10 or newer.

```text
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Commands

Machine output is JSON on stdout. Diagnostics go to stderr. `--output json` is the default and may be placed before or after the subcommand.

```text
searxng-python-cli version --output json
searxng-python-cli agent schema --output json
searxng-python-cli agent errors --output json
searxng-python-cli agent doctor --engines wikipedia --output json
searxng-python-cli engines list --limit 20 --output json
searxng-python-cli engines info sogou --output json
searxng-python-cli profiles list --output json
searxng-python-cli search "query" --profile general --limit 20 --output json
searxng-python-cli search "query" --profile fashion-images --limit 20 --output json
searxng-python-cli search "query" --engine wikipedia --timeout 25 --output json
```

From this checkout, before installation onto `PATH`:

```text
venv/Scripts/python.exe -I -m searxng_python_cli version --output json
```

`--limit` defaults to 20 and caps at 200. `--limit 0` returns the full list. Counts still report the uncut total. `--report-dir` writes the full report into a new directory inside the project; put it before the subcommand only if you also pass it as a global flag. It is accepted after the subcommand as well.

Images and videos are not the default. Use `--profile fashion-images`, `--profile fashion-videos`, or an explicit `--engines` list. `--category images` selects every non-key image engine and refuses more than 12 unless `--allow-large` is set.

Exit codes: 0 success, 1 engine or internal failure, 2 invalid input, 3 missing package or config, 4 timeout, 429, or captcha. Those rate-limit and captcha results are not retried and `retryable` is false.

## Coverage

Covered: engine inventory, local doctor, profile search, single-engine search, explicit engine lists, category selection, page, language, safesearch, and time range.

Not covered, because they belong to the SearXNG web application: HTTP API, Valkey, Docker, preferences, bangs, autocomplete, image proxy, and favicon proxy. A successful search returns result records and thumbnail URLs. It does not download image files.

One run with results does not mean those engines stay available.

## Layout

- `searxng_python_cli/`: command line and JSON envelope.
- `scripts/searxng_cli.py`: engine worker used by the command line.
- `scripts/settings.yml`: local settings merged with upstream settings.
- `config/profiles.json`: web, image, and video profiles.
- `skills/searxng-python-cli/SKILL.md`: agent operating notes.
