# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_cli", root / "scripts/searxng_cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
searx = cli.bootstrap(root, root / "scripts/settings.yml")
from searx.engines import load_engine, register_engine
from searx.network import initialize
from searx.search.models import SearchQuery, EngineRef
from searx.search.processors import ProcessorMap

selected = {"github": "Python", "currency": "10 USD to EUR", "tineye": "https://www.python.org/", "dictzone": "en-de hello"}
configs = [item for item in searx.settings["engines"] if item["name"] in selected]
initialize(settings_engines=configs)
records = []
for config in configs:
    engine = load_engine(config.copy())
    if engine is None:
        raise RuntimeError(f"无法加载 {config['name']}")
    register_engine(engine)
    processor = ProcessorMap.processor_types[engine.engine_type](engine)
    query = SearchQuery(selected[engine.name], [EngineRef(engine.name, engine.categories[0])], lang="en-US")
    params = processor.get_params(query, engine.categories[0])
    if params is None:
        raise ValueError(f"有效语法被拒绝 {engine.name}")
    records.append({"engine": engine.name, "engine_type": engine.engine_type, "query": query.query, "parameter_fields": sorted(params), "ok": True})
report = {"ok": True, "network_requests": False, "records": records, "offline": "默认 settings 没有 offline 实例；CLI 已使用上游 OfflineProcessor.get_params 和 engine.search 契约，未添加虚构实例"}
cli.save(root / "results/baseline-20261022/processor-params.json", report)
print(json.dumps(report, ensure_ascii=False, indent=2))
