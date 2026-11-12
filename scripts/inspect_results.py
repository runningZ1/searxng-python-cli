import json
from pathlib import Path
from lxml import html

root = Path(__file__).resolve().parents[1]
run = root / "results/baseline-20261022/run-20261022-200751"
report = {}
for name in ("github", "bing", "baidu", "wikibooks"):
    output = run / name
    record = json.loads((run / f"{name}.process.json").read_text(encoding="utf-8"))
    record["response"] = json.loads((output / "response.json").read_text(encoding="utf-8"))
    result_file = output / "results.json"
    if result_file.exists():
        items = json.loads(result_file.read_text(encoding="utf-8"))
        record["count"] = len(items)
        record["examples"] = [{"title": item["title"], "url": item["url"]} for item in items[:2]]
    if name in ("bing", "baidu"):
        dom = html.fromstring((output / "response.body").read_bytes())
        record["html_title"] = dom.xpath("string(//title)")
        record["visible_text_excerpt"] = " ".join(dom.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)]"))[:1600]
        record["bing_result_elements"] = len(dom.xpath('//ol[@id="b_results"]/li[contains(@class,"b_algo")]'))
    report[name] = record
(run / "inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
