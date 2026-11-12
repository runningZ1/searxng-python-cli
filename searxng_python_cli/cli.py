# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent-facing command surface over the existing SearXNG engine caller."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from searxng_python_cli import UPSTREAM_COMMIT, UPSTREAM_URL, __version__

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0"
DEFAULT_LIMIT = 20
MAX_LIMIT = 200
PROFILES = ["general", "fashion", "fashion-images", "fashion-videos"]
EXIT = {"ok": 0, "internal": 1, "usage": 2, "dependency": 3, "transient": 4, "conflict": 5}


def envelope(ok, payload, started, output):
    body = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "type": "result" if ok else "error",
        "meta": {
            "tool": "searxng-python-cli",
            "tool_version": __version__,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "upstream": UPSTREAM_URL,
            "upstream_commit": UPSTREAM_COMMIT,
        },
    }
    if ok:
        body["data"] = payload
    else:
        body["error"] = payload
    text = json.dumps(body, ensure_ascii=False)
    if output == "json":
        sys.stdout.write(text + "\n")
    return body


def fail(code, message, started, output, exit_code, retryable, next_command):
    error = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "outcome": "not_started",
        "details": {},
        "next_actions": [{"command": next_command}] if next_command else [],
    }
    if output == "json":
        envelope(False, error, started, "json")
    else:
        print(message, file=sys.stderr)
    return exit_code


def classify(stderr, exitcode):
    text = stderr.lower()
    if "429" in text or "too many" in text or "captcha" in text or "验证码" in stderr:
        return "RATE_LIMITED", False, EXIT["transient"]
    if "timed out" in text or "超时" in stderr:
        return "TIMEOUT", False, EXIT["transient"]
    if exitcode == 2 or "usage" in text or "unrecognized" in text or "invalid" in text or "必须" in stderr:
        return "INVALID_INPUT", False, EXIT["usage"]
    if "modulenotfounderror" in text or "no module named" in text:
        return "MISSING_DEPENDENCY", False, EXIT["dependency"]
    return "ENGINE_FAILED", False, EXIT["internal"]


def run_legacy(root, config, report_dir, args):
    command = [sys.executable, "-I", str(root / "scripts/searxng_cli.py"), "--root", str(root), "--config", str(config)]
    if report_dir:
        command.extend(["--output", str(report_dir)])
    command.extend(args)
    process = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8")
    data = None
    if process.stdout.strip():
        try:
            data = json.loads(process.stdout)
        except json.JSONDecodeError:
            data = None
    return process.returncode, data, process.stderr


def bound(items, limit):
    if limit == 0:
        return items, False
    return items[:limit], len(items) > limit


def with_thumbnail(items):
    output = []
    for item in items:
        if isinstance(item, dict) and not item.get("thumbnail"):
            item = dict(item)
            item["thumbnail"] = item.get("thumbnail_src") or item.get("img_src") or ""
        output.append(item)
    return output
class CLIParser(argparse.ArgumentParser):
    def error(self, message):
        body = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "type": "error",
            "error": {
                "code": "INVALID_INPUT",
                "message": message,
                "retryable": False,
                "outcome": "not_started",
                "details": {},
                "next_actions": [{"command": "searxng-python-cli --help"}],
            },
            "meta": {"tool": "searxng-python-cli", "tool_version": __version__},
        }
        sys.stdout.write(json.dumps(body, ensure_ascii=False) + "\n")
        raise SystemExit(EXIT["usage"])


def parser():
    common = CLIParser(add_help=False)
    common.add_argument("--output", choices=["json", "text"], default="json")
    common.add_argument("--quiet", action="store_true")
    common.add_argument("--root", type=Path, default=ROOT)
    common.add_argument("--config", type=Path)
    common.add_argument("--report-dir", type=Path, help="Write the full legacy report. Must be a new directory inside the project.")
    main = CLIParser(prog="searxng-python-cli", description="Call SearXNG engines without starting the web application.", parents=[common])
    commands = main.add_subparsers(dest="command", required=True)
    commands.add_parser("version", parents=[common], help="Print the CLI and upstream pin.")
    agent = commands.add_parser("agent", parents=[common], help="Discovery for agents.")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    agent_commands.add_parser("schema", parents=[common])
    agent_commands.add_parser("errors", parents=[common])
    doctor = agent_commands.add_parser("doctor", parents=[common])
    doctor.add_argument("--initialize", action="store_true")
    doctor.add_argument("--engines", nargs="+")
    doctor.add_argument("--timeout", type=float, default=20)
    doctor.add_argument("--workers", type=int, default=4)
    engines = commands.add_parser("engines", parents=[common])
    engine_commands = engines.add_subparsers(dest="engines_command", required=True)
    listed = engine_commands.add_parser("list", parents=[common])
    listed.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    listed.add_argument("--category")
    info = engine_commands.add_parser("info", parents=[common])
    info.add_argument("name")
    profiles = commands.add_parser("profiles", parents=[common])
    profile_commands = profiles.add_subparsers(dest="profiles_command", required=True)
    profile_commands.add_parser("list", parents=[common])
    search = commands.add_parser("search", parents=[common], help="Search one engine, a profile, or an explicit engine list.")
    search.add_argument("query")
    search.add_argument("--engine")
    search.add_argument("--engines", nargs="+")
    search.add_argument("--profile", choices=PROFILES)
    search.add_argument("--category")
    search.add_argument("--allow-large", action="store_true", help="Allow a category to select more than 12 engines.")
    search.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--language", default="en-US")
    search.add_argument("--time-range", choices=["day", "week", "month", "year"])
    search.add_argument("--safesearch", type=int, choices=[0, 1, 2], default=0)
    search.add_argument("--timeout", type=float, default=30)
    search.add_argument("--workers", type=int, default=4)
    search.add_argument("--terms", nargs="+")
    return main


def schema():
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "upstream": {"url": UPSTREAM_URL, "commit": UPSTREAM_COMMIT},
        "default_limit": DEFAULT_LIMIT,
        "max_limit": MAX_LIMIT,
        "unlimited_limit": 0,
        "commands": [
            {"name": "version", "effect": "read-only", "idempotent": True},
            {"name": "agent schema", "effect": "read-only", "idempotent": True},
            {"name": "agent errors", "effect": "read-only", "idempotent": True},
            {"name": "agent doctor", "effect": "read-only", "idempotent": True, "note": "--initialize may contact engine setup endpoints"},
            {"name": "engines list", "effect": "read-only", "idempotent": True},
            {"name": "engines info", "effect": "read-only", "idempotent": True},
            {"name": "profiles list", "effect": "read-only", "idempotent": True},
            {"name": "search", "effect": "read-only-network", "idempotent": False, "retryable": False, "note": "Live web results change. 429 and captcha are not retried."},
        ],
        "not_covered": [
            "SearXNG web application, HTTP API, Valkey, Docker",
            "preferences, bangs, autocomplete, image proxy, favicon proxy",
            "persisting engine enablement or editing upstream settings",
        ],
    }


def errors():
    return {
        "exit_codes": [
            {"exit": 0, "meaning": "all selected engines returned"},
            {"exit": 1, "meaning": "engine or internal failure; do not assume a retry"},
            {"exit": 2, "meaning": "invalid arguments"},
            {"exit": 3, "meaning": "searxng package or config missing"},
            {"exit": 4, "meaning": "timeout, 429, or captcha; retryable is false"},
            {"exit": 5, "meaning": "reserved for conflict; unused"},
        ],
        "codes": ["INVALID_INPUT", "MISSING_DEPENDENCY", "RATE_LIMITED", "TIMEOUT", "ENGINE_FAILED", "LIMIT_EXCEEDED"],
    }


def check_limit(limit):
    if limit < 0 or (limit > MAX_LIMIT):
        raise ValueError(f"--limit must be 0 through {MAX_LIMIT}")


def main(argv=None):
    started = time.monotonic()
    args = parser().parse_args(argv)
    output = args.output
    root = args.root.resolve()
    config = (args.config or root / "scripts/settings.yml").resolve()
    try:
        if args.command == "version":
            data = {"version": __version__, "upstream_url": UPSTREAM_URL, "upstream_commit": UPSTREAM_COMMIT}
            if output == "text":
                print(f"searxng-python-cli {__version__} upstream {UPSTREAM_COMMIT}")
            envelope(True, data, started, output)
            return 0
        if args.command == "agent" and args.agent_command == "schema":
            envelope(True, schema(), started, output)
            return 0
        if args.command == "agent" and args.agent_command == "errors":
            envelope(True, errors(), started, output)
            return 0
        if args.command == "profiles":
            path = root / "config/profiles.json"
            if not path.exists():
                return fail("MISSING_DEPENDENCY", f"missing {path}", started, output, EXIT["dependency"], False, "copy config/profiles.json into the project")
            payload = json.loads(path.read_text(encoding="utf-8"))
            envelope(True, payload, started, output)
            return 0
        if hasattr(args, "limit"):
            check_limit(args.limit)
        if args.command == "agent" and args.agent_command == "doctor":
            legacy = ["doctor", "--timeout", str(args.timeout), "--workers", str(args.workers)]
            if args.initialize:
                legacy.append("--initialize")
            if args.engines:
                legacy.extend(["--engines", *args.engines])
            code, data, stderr = run_legacy(root, config, args.report_dir, legacy)
        elif args.command == "engines" and args.engines_command == "info":
            code, data, stderr = run_legacy(root, config, args.report_dir, ["info", args.name])
        elif args.command == "engines":
            code, data, stderr = run_legacy(root, config, args.report_dir, ["list"])
            if code == 0 and data:
                engines = data["engines"]
                if args.category:
                    engines = [item for item in engines if args.category in item.get("categories", [])]
                shown, truncated = bound(engines, args.limit)
                data = {"applied_limit": args.limit, "returned_count": len(shown), "total_count": len(engines), "truncated": truncated, "engines": shown}
        elif args.command == "search":
            selectors = [bool(args.engine), bool(args.engines), bool(args.profile), bool(args.category)]
            if sum(selectors) != 1:
                return fail("INVALID_INPUT", "pass exactly one of --engine, --engines, --profile, or --category", started, output, EXIT["usage"], False, "searxng-python-cli search --help")
            if args.query == "-":
                args.query = sys.stdin.read().strip()
            if args.engine:
                legacy = ["search", args.engine, args.query, "--page", str(args.page), "--language", args.language, "--safesearch", str(args.safesearch), "--timeout", str(args.timeout)]
                if args.category:
                    legacy.extend(["--category", args.category])
                if args.time_range:
                    legacy.extend(["--time-range", args.time_range])
                code, data, stderr = run_legacy(root, config, args.report_dir, legacy)
            else:
                names = list(args.engines or [])
                if args.category:
                    list_code, listed, list_err = run_legacy(root, config, None, ["list"])
                    if list_code != 0 or not listed:
                        code, data, stderr = list_code, listed, list_err
                        names = []
                    else:
                        names = [item["name"] for item in listed["engines"] if args.category in item.get("categories", []) and not item.get("disabled") and not item.get("require_api_key")]
                        if not names:
                            return fail("INVALID_INPUT", f"category {args.category} selected no engines", started, output, EXIT["usage"], False, "searxng-python-cli engines list --category " + args.category)
                        if len(names) > 12 and not args.allow_large:
                            return fail("LIMIT_EXCEEDED", f"category {args.category} selects {len(names)} engines; pass --engines or --allow-large", started, output, EXIT["usage"], False, "searxng-python-cli search QUERY --profile fashion-images")
                legacy = ["parallel", args.query, "--workers", str(args.workers), "--page", str(args.page), "--language", args.language, "--safesearch", str(args.safesearch), "--timeout", str(args.timeout)]
                if args.profile:
                    legacy.extend(["--profile", args.profile])
                else:
                    legacy.extend(["--engines", *names])
                if args.terms:
                    legacy.extend(["--terms", *args.terms])
                if args.time_range:
                    legacy.extend(["--time-range", args.time_range])
                if names or args.profile:
                    code, data, stderr = run_legacy(root, config, args.report_dir, legacy)
            if code == 0 and data and "results" in data:
                shown, truncated = bound(data["results"], args.limit)
                data = dict(data)
                data["results"] = with_thumbnail(shown)
                data["applied_limit"] = args.limit
                data["truncated"] = truncated
                if "matched" in data:
                    matched, matched_truncated = bound(data["matched"], args.limit)
                    data["matched"] = matched
                    data["matched_truncated"] = matched_truncated
        else:
            return fail("INVALID_INPUT", "unknown command", started, output, EXIT["usage"], False, "searxng-python-cli --help")
    except ValueError as exc:
        return fail("INVALID_INPUT", str(exc), started, output, EXIT["usage"], False, "searxng-python-cli --help")
    if code == 0 and data is not None:
        if output == "text":
            count = data.get("returned_count", data.get("count", data.get("total_count")))
            print(f"ok count={count}")
        envelope(True, data, started, output)
        return 0
    error_code, retryable, exit_code = classify(stderr or "", code)
    message = (stderr or "command failed").strip().splitlines()
    text = message[-1] if message else "command failed"
    if data and data.get("counts"):
        text = json.dumps(data["counts"], ensure_ascii=False)
    return fail(error_code, text, started, output, exit_code, retryable, "searxng-python-cli agent doctor --output json")


if __name__ == "__main__":
    sys.exit(main())
