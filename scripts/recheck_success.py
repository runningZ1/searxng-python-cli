# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from threading import Timer

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "results/full-audit-20261022-231500"


def stamp():
    now = dt.datetime.now().astimezone()
    return {"utc": now.astimezone(dt.timezone.utc).isoformat(), "local": now.isoformat()}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize(text):
    text = re.sub(r"https?://[^\s<>\"']+", "[URL omitted]", text)
    text = re.sub(r"(?i)((?:api.?key|token|password|secret|authorization|cookie)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    return text


def targets():
    rows = []
    for path in sorted((PRIOR / "items").glob("*/record.json")):
        record = load(path)
        if record.get("status") != "success":
            continue
        rows.append({
            "prior_item": path.parent.name,
            "engine": record["engine"],
            "engine_module": record["engine_module"],
            "query": record["query"],
            "source_group": record["source_group"],
            "theme": record.get("theme"),
            "prior_results_count": record.get("results_count"),
            "prior_safesearch": record.get("query_options", {}).get("safesearch", 0),
        })
    if len(rows) != 147:
        raise SystemExit(f"上次有结果实例数量不是 147：{len(rows)}")
    return rows


def execute(row, directory, timeout):
    safesearch = row["prior_safesearch"]
    args = [
        str(ROOT / "venv/Scripts/python.exe"), "-I", str(ROOT / "scripts/searxng_cli.py"),
        "_search", row["engine"], row["query"], "--timeout", str(timeout), "--safesearch", str(safesearch),
    ]
    stderr_path = directory / "stderr.txt"
    stdout_path = directory / "stdout.json"
    process = subprocess.Popen(args, cwd=ROOT / "scripts", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    expired = []

    def terminate():
        expired.append(True)
        process.kill()

    timer = Timer(timeout + 15, terminate)
    timer.start()
    stdout, stderr = process.communicate()
    timer.cancel()
    error = sanitize(stderr.decode("utf-8", errors="replace"))
    stderr_path.write_text(error, encoding="utf-8")
    result = {
        "process_exitcode": process.returncode,
        "network_request_confirmed": False,
        "stderr_evidence": str(stderr_path.relative_to(ROOT)),
        "error_type": None,
        "results_count": None,
    }
    if expired:
        result.update(status="timeout", error_type="HardProcessTimeout")
    elif process.returncode:
        lines = [line for line in error.splitlines() if line.strip()]
        last = lines[-1] if lines else "ChildProcessError"
        exception_types = re.findall(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Timeout)):", error, flags=re.M)
        kind = exception_types[-1] if exception_types else last.split(":", 1)[0]
        if "429" in error or "TooManyRequests" in error:
            status = "rate_limited"
        elif re.search(r"captcha|botdetected|bot detected|unusual traffic", error, re.I):
            status = "captcha"
        elif re.search(r"timeout|timed out", kind, re.I):
            status = "timeout"
        else:
            status = "error"
        result.update(status=status, error_type=kind, error_summary=last)
        result["network_request_confirmed"] = bool(re.search(r"HTTP|curl|requests|SearxEngineTooManyRequests|Captcha|CAPTCHA", error))
    else:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
        count = data["count"]
        stdout_path.write_text(json.dumps({"ok": data["ok"], "engine": data["engine"], "engine_module": data["engine_module"], "engine_type": data["engine_type"], "query": data["query"], "count": count}, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update(status="success" if count else "empty", results_count=count, network_request_confirmed=True, results_evidence=str(stdout_path.relative_to(ROOT)))
    return result


def overview(directory, rows):
    records = [load(path) for path in sorted((directory / "items").glob("*/record.json"))]
    summary = {
        "updated": stamp(),
        "selected": len(rows),
        "completed": len(records),
        "remaining": len(rows) - len(records),
        "counts": dict(Counter(record["status"] for record in records)),
        "still_success": sum(record["status"] == "success" for record in records),
    }
    save(directory / "progress.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args()
    if args.interval < 1 or args.timeout <= 0:
        raise SystemExit("interval 至少 1 秒，timeout 必须大于零")
    directory = args.output.resolve()
    if not directory.is_relative_to(ROOT / "results"):
        raise SystemExit("输出目录必须位于 results 内")
    directory.mkdir(exist_ok=args.resume)
    (directory / "items").mkdir(exist_ok=args.resume)
    rows = targets()
    if not args.resume:
        save(directory / "plan.json", rows)
        save(directory / "manifest.json", {
            "started": stamp(),
            "source": "results/full-audit-20261022-231500 status=success",
            "selected": len(rows),
            "interval_seconds": args.interval,
            "hard_timeout_seconds": args.timeout + 15,
            "query_policy": "沿用上次成功查询与 safesearch；不重试 429 或验证码来源组",
        })
    stopped = set()
    for path in (directory / "items").glob("*/record.json"):
        record = load(path)
        if record["status"] in ("rate_limited", "captcha"):
            stopped.add(record["source_group"])
    last_finished = 0.0
    for index, row in enumerate(rows):
        item = directory / "items" / f"{index + 1:03d}"
        record_path = item / "record.json"
        if record_path.exists():
            continue
        item.mkdir(exist_ok=True)
        reason = "source_group_stopped_after_429_or_captcha" if row["source_group"] in stopped else None
        record = {**row, "started": stamp(), "evidence": str(record_path.relative_to(ROOT))}
        if reason:
            record.update(status="blocked", blocked_reason=reason, results_count=None, error_type=None, network_request_confirmed=False)
        else:
            remaining_wait = args.interval - (time.monotonic() - last_finished)
            if remaining_wait > 0 and last_finished:
                time.sleep(remaining_wait)
            record.update(execute(row, item, args.timeout))
            last_finished = time.monotonic()
            if record["status"] in ("rate_limited", "captcha"):
                stopped.add(row["source_group"])
        record["ended"] = stamp()
        save(record_path, record)
        progress = overview(directory, rows)
        print(json.dumps({"processed": progress["completed"], "remaining": progress["remaining"], "engine": row["engine"], "status": record["status"], "count": record.get("results_count"), "counts": progress["counts"]}, ensure_ascii=False), flush=True)
    progress = overview(directory, rows)
    save(directory / "completed.json", {"ended": stamp(), **progress})


if __name__ == "__main__":
    main()
