import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
doctor = json.loads((root / "results/doctor-20261022/report.json").read_text(encoding="utf-8"))
audit = json.loads((root / "results/full-audit-20261022-231500/all-352.json").read_text(encoding="utf-8"))
prior = {row["engine"]: row for row in audit}
rows = []
for record in doctor["records"]:
    data = record["data"] or {}
    name = record["engine"]
    previous = prior[name]
    rows.append({
        "engine": name,
        "engine_module": data.get("engine_module") or previous["engine_module"],
        "engine_type": data.get("engine_type") or previous.get("engine_type"),
        "doctor_status": record["status"],
        "require_api_key": data.get("require_api_key"),
        "missing": data.get("missing_required_attributes") or [],
        "active": data.get("active"),
        "auth": previous.get("auth"),
        "prior_status": previous.get("status"),
        "prior_count": previous.get("results_count"),
        "query": previous.get("query") or "python",
    })

no_key = [row for row in rows if row["require_api_key"] is False and row["doctor_status"] in ("local_inspected", "initialization_pending") and not row["missing"]]
print(json.dumps({
    "configured": len(rows),
    "require_api_key": dict(Counter(str(row["require_api_key"]) for row in rows)),
    "doctor": dict(Counter(row["doctor_status"] for row in rows)),
    "auth": dict(Counter(row["auth"] for row in rows)),
    "prior_status": dict(Counter(row["prior_status"] for row in rows)),
    "no_key_runnable": len(no_key),
    "no_key_prior_success": sum(row["prior_status"] == "success" for row in no_key),
    "prior_success_outside_no_key": [row["engine"] for row in rows if row["prior_status"] == "success" and row not in no_key],
}, ensure_ascii=False, indent=2))
(root / "results/no-key-candidates.json").write_text(json.dumps(no_key, ensure_ascii=False, indent=2), encoding="utf-8")
