# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from collections import Counter
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("report", type=Path)
args = parser.parse_args()
report = json.loads(args.report.read_text(encoding="utf-8"))
if "engines" in report:
    entries = report["engines"]
    result = {"count": len(entries), "engine_types": dict(Counter(item["engine_type"] for item in entries)), "formats": dict(Counter(str(item["results_format"]) for item in entries)), "generic_examples": [{"name": item["name"], "module": item["engine_module"]} for item in entries if item["engine_module"] in ("json_engine", "xpath") and not item["inactive"]], "offline": [item["name"] for item in entries if item["engine_type"] != "online"]}
else:
    result = {"counts": report["counts"], "examples": [{"engine": item["engine"], "status": item["status"], "count": item.get("data", {}).get("count") if item.get("data") else None, "first": item.get("data", {}).get("results", [])[:1] if item.get("data") else None} for item in report["records"] if report["mode"] == "batch" or item["status"] in ("configuration_missing", "load_or_initialization_failed")]}
print(json.dumps(result, ensure_ascii=False, indent=2))
