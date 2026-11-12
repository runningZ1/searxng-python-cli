# SPDX-License-Identifier: AGPL-3.0-or-later
from collections import Counter
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def read(path):
    return json.loads((root / path).read_text(encoding="utf-8"))

catalog = read("results/catalog-20261022/report.json")
doctor = read("results/doctor-20261022/report.json")
network = read("results/baseline-20261022/network/report.json")
typed = read("results/baseline-20261022/typed-crossref/report.json")
records = []
for item in network["records"]:
    data = item["data"]
    records.append({"engine": item["engine"], "status": item["status"], "count": data["count"] if data else None, "engine_type": data["engine_type"] if data else None, "error": item["stderr"].strip().splitlines()[-1] if not data else None, "evidence": "results/baseline-20261022/network/report.json"})
records.append({"engine": typed["engine"], "status": "success", "count": typed["count"], "result_types": sorted({item.get("result_type", "legacy") for item in typed["results"]}), "evidence": "results/baseline-20261022/typed-crossref/report.json"})
summary = {"configuration_count": catalog["count"], "configured_module_count": catalog["module_count"], "source_module_count": catalog["source_module_count"], "unconfigured_modules": catalog["unconfigured_modules"], "engine_types": dict(Counter(item["engine_type"] for item in catalog["engines"])), "disabled": sum(item["disabled"] for item in catalog["engines"]), "inactive": sum(item["inactive"] for item in catalog["engines"]), "doctor_counts": doctor["counts"], "missing_configuration": [{"engine": item["engine"], "attributes": item["data"]["missing_required_attributes"]} for item in doctor["records"] if item["status"] == "configuration_missing"], "network": records, "actual_network_selected": len(records), "network_unverified": catalog["count"] - len(records), "processor_parameters": "results/baseline-20261022/processor-params.json", "doctor_evidence": "results/doctor-20261022/report.json", "scope": "全部默认配置已发现并执行本地导入、属性、traits检查；setup/init有副作用时待显式调用；仅7个实例做实际网络验证，6成功1限流；offline默认配置为零，未虚构实例。"}
(root / "results/baseline-20261022/validation-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
