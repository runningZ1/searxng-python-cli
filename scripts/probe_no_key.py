# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    now = dt.datetime.now().astimezone()
    return now.astimezone(dt.timezone.utc).isoformat()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--query", help="普通网页、图片、视频、新闻类实例使用的查询；词典、货币、URL 类保留各自可执行查询")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    directory = args.output.resolve()
    if not directory.is_relative_to(ROOT / "results"):
        raise SystemExit("输出目录必须位于 results 内")
    directory.mkdir(exist_ok=args.resume)
    rows = load(ROOT / "results/no-key-candidates.json")
    specialized = {"en-de hello", "10 USD to EUR", "https://www.python.org/"}
    groups = defaultdict(list)
    for row in rows:
        query = row["query"] if row["query"] in specialized or not args.query else args.query
        groups[query].append(row)
    if args.chunk < 1:
        raise SystemExit("chunk 必须大于零")
    summary = {"started": stamp(), "candidates": len(rows), "requested_query": args.query, "workers": args.workers, "chunk": args.chunk, "timeout": args.timeout, "groups": {}}
    for query, items in groups.items():
        names = [item["engine"] for item in items]
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        collected = []
        for index in range(0, len(names), args.chunk):
            chunk = names[index:index + args.chunk]
            target = directory / f"query-{digest}-{index // args.chunk:02d}.json"
            if args.resume and target.exists():
                data = load(target)
            else:
                raw = directory / f"raw-{digest}-{index // args.chunk:02d}"
                command = [sys.executable, "-I", str(ROOT / "scripts/searxng_cli.py"), "--output", str(raw), "parallel", "--engines", *chunk, "--workers", str(min(args.workers, len(chunk))), "--timeout", str(args.timeout), query]
                completed = subprocess.run(command, cwd=ROOT / "scripts")
                report = raw / "report.json"
                data = load(report) if report.exists() else {"ok": False, "query": query, "counts": {}, "engines": []}
                data["exitcode"] = completed.returncode
                save(target, {"query": query, "offset": index, "exitcode": completed.returncode, "counts": data.get("counts"), "engines": data.get("engines", [])})
            collected.extend(data.get("engines", []))
            print(json.dumps({"query": query, "offset": index, "selected": len(chunk), "counts": data.get("counts")}, ensure_ascii=False), flush=True)
        summary["groups"][query] = {"selected": len(names), "returned": len(collected)}
    engines = []
    for path in directory.glob("query-*.json"):
        engines.extend(load(path)["engines"])
    by_status = Counter("success" if item.get("ok") and item.get("count") else "empty" if item.get("ok") else "failed" for item in engines)
    elapsed = sorted(item.get("elapsed_seconds") or 0 for item in engines)
    def percentile(fraction):
        if not elapsed:
            return None
        return elapsed[min(len(elapsed) - 1, int((len(elapsed) - 1) * fraction))]
    success_elapsed = sorted(item.get("elapsed_seconds") or 0 for item in engines if item.get("ok") and item.get("count"))
    summary.update(ended=stamp(), tested=len(engines), counts=dict(by_status), elapsed_seconds={"min": elapsed[0] if elapsed else None, "p50": percentile(0.5), "p90": percentile(0.9), "max": elapsed[-1] if elapsed else None, "success_p50": success_elapsed[len(success_elapsed)//2] if success_elapsed else None}, success=[{"engine": item["engine"], "count": item["count"], "elapsed_seconds": item.get("elapsed_seconds")} for item in engines if item.get("ok") and item.get("count")], empty=[item["engine"] for item in engines if item.get("ok") and not item.get("count")], failed=[{"engine": item["engine"], "error": item.get("error"), "timed_out": item.get("timed_out"), "elapsed_seconds": item.get("elapsed_seconds")} for item in engines if not item.get("ok")])
    save(directory / "summary.json", summary)
    print(json.dumps({"tested": summary["tested"], "counts": summary["counts"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
