# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_QUERIES = {"online_dictionary": "en-de hello", "online_currency": "10 USD to EUR", "online_url_search": "https://www.python.org/"}


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=encode)


def encode(value):
    import msgspec
    if isinstance(value, msgspec.Struct):
        from searx.result_types import Result
        if isinstance(value, Result):
            return {"result_type": type(value).__name__, **value.as_dict()}
        return msgspec.structs.asdict(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"不支持的结果类型：{type(value).__name__}")


def save(path, value):
    path.write_text(dump(value), encoding="utf-8")


def environment(root, config):
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("SEARX") or name.startswith("GIT_"):
            del env[name]
    for name, folder in {"TEMP": "temp", "TMP": "temp", "XDG_CACHE_HOME": "cache", "XDG_DATA_HOME": "data", "XDG_CONFIG_HOME": "config", "PIP_CACHE_DIR": "pip-cache"}.items():
        target = root / folder
        target.mkdir(exist_ok=True)
        env[name] = str(target)
    env["SEARXNG_SETTINGS_PATH"] = str(config)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def engine_dir():
    import searx.engines
    return Path(searx.engines.__file__).resolve().parent


def bootstrap(root, config):
    env = environment(root, config)
    os.environ.clear()
    os.environ.update(env)
    sys.dont_write_bytecode = True
    import logging
    logging.disable(logging.CRITICAL)
    import searx
    return searx


def literals(tree):
    values = {}
    allowed = (ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Load, ast.UnaryOp, ast.USub)
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(item, allowed) for item in ast.walk(node.value)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = ast.literal_eval(node.value)
    return values


def catalog(root, settings):
    output = []
    for config in settings["engines"]:
        path = engine_dir() / (config["engine"] + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values = literals(tree)
        values.update(config)
        about = values.get("about", {})
        hooks = [item.name for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        imports = sorted({item.module.split(".")[0] for item in ast.walk(tree) if isinstance(item, ast.ImportFrom) and item.module} | {alias.name.split(".")[0] for item in ast.walk(tree) if isinstance(item, ast.Import) for alias in item.names})
        missing = sorted(name for name, value in values.items() if value is None and not name.startswith("_"))
        output.append({"name": config["name"], "engine_module": config["engine"], "disabled": config.get("disabled", False), "inactive": config.get("inactive", False), "engine_type": values.get("engine_type", "online"), "categories": values.get("categories", ["general"]), "require_api_key": about.get("require_api_key") if isinstance(about, dict) else None, "results_format": about.get("results") if isinstance(about, dict) else None, "required_missing_literal_attributes": missing, "configuration_fields": sorted(config), "has_setup": "setup" in hooks, "has_init": "init" in hooks, "imports": imports, "source_file": str(path), "requirements_source": "模块公开 None 属性、setup/init 和对应上游文档；动态条件由 doctor 校验", "network_requirement": "offline 仍可能需要数据库、本地命令或服务" if values.get("engine_type") == "offline" else "远程 HTTP 服务；setup/init 可能另有外部请求", "command": [str(root / "venv/Scripts/python.exe"), "-I", str(root / "scripts/searxng_cli.py"), "search", config["name"], EXAMPLE_QUERIES.get(values.get("engine_type"), "Python")]})
    return output


def probe(config, initialize):
    from searx.engines import ENGINE_DIR, update_engine_attributes, update_attributes_for_tor, check_engine_module, is_engine_active, set_loggers, register_engine
    from searx.utils import load_module
    from searx.enginelib.traits import EngineTraitsMap
    from searx.search.processors import ProcessorMap
    engine = load_module(config["engine"] + ".py", ENGINE_DIR)
    check_engine_module(engine)
    update_engine_attributes(engine, config)
    update_attributes_for_tor(engine)
    EngineTraitsMap.from_data().set_traits(engine)
    missing = [name for name in dir(engine) if not name.startswith("_") and getattr(engine, name) is None]
    supported = engine.engine_type in ProcessorMap.processor_types
    active = is_engine_active(engine)
    record = {"name": config["name"], "engine_module": config["engine"], "engine_type": engine.engine_type, "disabled": engine.disabled, "inactive": engine.inactive, "active": active, "missing_required_attributes": missing, "require_api_key": engine.about.require_api_key, "results_format": engine.about.results, "categories": engine.categories, "paging": engine.paging, "time_range_support": engine.time_range_support, "safesearch": engine.safesearch, "language_support": engine.language_support, "has_setup": hasattr(engine, "setup"), "has_init": hasattr(engine, "init"), "processor_supported": supported, "status": "local_inspected", "network_verified": False}
    if missing:
        record["status"] = "configuration_missing"
    elif not active:
        record["status"] = "inactive_or_tor_required"
    elif not supported:
        record["status"] = "unsupported_processor"
    elif hasattr(engine, "setup") or hasattr(engine, "init"):
        record["status"] = "initialization_pending"
    if initialize and record["status"] in ("local_inspected", "initialization_pending"):
        set_loggers(engine, engine.name)
        register_engine(engine)
        from searx.network import initialize as initialize_network
        initialize_network(settings_engines=[config])
        processor = ProcessorMap.processor_types[engine.engine_type](engine)
        if hasattr(processor, "init_network_in_thread"):
            processor.init_network_in_thread(time.monotonic(), engine.timeout)
        if hasattr(engine, "setup") and engine.setup(config) is False:
            raise RuntimeError("上游 setup 返回 False")
        if hasattr(engine, "init") and engine.init(config) is False:
            raise RuntimeError("上游 init 返回 False")
        record["status"] = "initialized"
    return record


def search(config, args):
    from searx.engines import load_engine, register_engine
    from searx.network import initialize
    from searx.search.processors import ProcessorMap
    from searx.search.models import SearchQuery, EngineRef
    engine = load_engine(config.copy())
    if engine is None:
        raise RuntimeError("上游拒绝加载此配置；运行 doctor 查看缺失配置、inactive 或 Tor 条件")
    register_engine(engine)
    if engine.engine_type not in ProcessorMap.processor_types:
        raise ValueError(f"不支持的 engine_type：{engine.engine_type}")
    initialize(settings_engines=[config])
    processor = ProcessorMap.processor_types[engine.engine_type](engine)
    if hasattr(processor, "init_network_in_thread"):
        processor.init_network_in_thread(time.monotonic(), args.timeout)
    if hasattr(engine, "init") and engine.init(config) is False:
        raise RuntimeError("上游 init 返回 False")
    category = args.category or engine.categories[0]
    if category not in engine.categories:
        raise ValueError(f"渠道不支持 category：{category}")
    query = SearchQuery(args.query, [EngineRef(engine.name, category)], lang=args.language, pageno=args.page, time_range=args.time_range, safesearch=args.safesearch, timeout_limit=args.timeout)
    params = processor.get_params(query, category)
    if params is None:
        raise ValueError("上游拒绝查询参数：检查分页、时间范围或该处理器的专用查询语法")
    if engine.engine_type == "offline":
        results = engine.search(args.query, params)
    else:
        engine.request(args.query, params)
        if not params["url"]:
            raise ValueError("上游 request 未产生 URL；此查询不符合引擎要求")
        response = processor._send_http_request(params)
        response.search_params = params
        results = engine.response(response)
    if not isinstance(results, list):
        raise TypeError(f"上游返回不支持的结果容器：{type(results).__name__}")
    return {"ok": True, "engine": engine.name, "engine_module": config["engine"], "engine_type": engine.engine_type, "query": args.query, "count": len(results), "results": results}


def redact(text, config):
    import yaml
    from urllib.parse import quote, quote_plus
    values = yaml.safe_load(config.read_text(encoding="utf-8"))
    def clean(value):
        nonlocal text
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"key|token|secret|password|credential|auth", str(key), re.I) and isinstance(item, str) and item:
                    for secret in {item, quote(item, safe=""), quote_plus(item)}:
                        text = text.replace(secret, "[REDACTED]")
                clean(item)
        elif isinstance(value, list):
            for item in value:
                clean(item)
    clean(values)
    text = re.sub(r"(?i)([?&](?:api[_-]?key|token|key|password|secret|access_token)=)[^&\s\"']+", r"\1[REDACTED]", text)
    return text


def text_of(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(text_of(item) for item in value if text_of(item))
    if isinstance(value, dict):
        for key in ("name", "title", "value", "text"):
            if key in value and text_of(value[key]):
                return text_of(value[key])
    return ""


def structured_item(item, engine):
    if not isinstance(item, dict):
        return {"engine": engine, "result_type": type(item).__name__, "title": text_of(item), "url": "", "content": "", "published": None}
    title = text_of(item.get("title") or item.get("answer") or item.get("suggestion") or item.get("correction") or item.get("infobox"))
    content = text_of(item.get("content") or item.get("abstract") or item.get("snippet"))
    published = item.get("publishedDate") or item.get("pubdate") or item.get("published")
    if isinstance(published, dict):
        published = published.get("datetime") or published.get("date")
    return {
        "engine": item.get("engine") or engine,
        "result_type": item.get("result_type") or item.get("template") or "legacy",
        "title": title,
        "url": text_of(item.get("url") or item.get("iframe_src") or item.get("audio_src")),
        "content": content,
        "published": published if isinstance(published, str) else None,
        "thumbnail": text_of(item.get("thumbnail") or item.get("img_src")),
        "authors": item.get("authors") if isinstance(item.get("authors"), list) else [],
    }


def search_command(engine, query, args):
    command = ["_search", engine, query, "--page", str(args.page), "--language", args.language, "--safesearch", str(args.safesearch), "--timeout", str(args.timeout)]
    for name in ("category", "time_range"):
        if getattr(args, name):
            command.extend(["--" + name.replace("_", "-"), getattr(args, name)])
    return command


def search_record(root, config_path, engine, query, args):
    started = time.monotonic()
    record = child(root, config_path, search_command(engine, query, args), args.timeout + 10)
    elapsed = round(time.monotonic() - started, 3)
    if record["exitcode"] == 0 and record["data"]:
        data = record["data"]
        items = [structured_item(item, engine) for item in data["results"]]
        return {"ok": True, "engine": data["engine"], "engine_module": data["engine_module"], "engine_type": data["engine_type"], "query": data["query"], "count": len(items), "elapsed_seconds": elapsed, "results": items}
    error = record["stderr"].strip().splitlines()
    return {"ok": False, "engine": engine, "query": query, "count": 0, "elapsed_seconds": elapsed, "exitcode": record["exitcode"], "timed_out": record["timed_out"], "error": error[-1] if error else "ChildProcessError", "results": []}


def load_selection(root):
    candidates = [root / "config/profiles.json", root / "docs/notes/channel-selection.json"]
    path = next((item for item in candidates if item.exists()), None)
    if path is None:
        raise FileNotFoundError("缺少渠道选择文件：config/profiles.json")
    return json.loads(path.read_text(encoding="utf-8"))


def select_engines(root, profile):
    selection = load_selection(root)
    profile_data = selection["profiles"][profile]
    names = []
    for group in profile_data["groups"]:
        names.extend(selection["groups"][group])
    excluded = set(profile_data.get("exclude", []))
    return [name for name in names if name not in excluded], profile_data


def relevant(item, terms):
    text = " ".join(text_of(item.get(key)) for key in ("title", "content", "url")).casefold()
    return any(term.casefold() in text for term in terms)


def timed(records):
    rows = []
    for record in sorted(records, key=lambda item: item.get("elapsed_seconds") or 0, reverse=True):
        rows.append({"engine": record["engine"], "ok": record["ok"], "count": record["count"], "elapsed_seconds": record.get("elapsed_seconds"), "error": record.get("error")})
    elapsed = [row["elapsed_seconds"] for row in rows if row["elapsed_seconds"] is not None]
    return {"per_engine": rows, "seconds": {"min": min(elapsed) if elapsed else None, "max": max(elapsed) if elapsed else None}}


def parallel_search(root, config_path, names, query, args):
    if args.workers < 1:
        raise ValueError("workers 必须大于零")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(args.workers, len(names))) as executor:
        records = list(executor.map(lambda name: search_record(root, config_path, name, query, args), names))
    wall = round(time.monotonic() - started, 3)
    results = [item for record in records for item in record["results"]]
    terms = [args.query] if not getattr(args, "terms", None) else args.terms
    matched = [item for item in results if relevant(item, terms)]
    return {
        "ok": all(item["ok"] for item in records),
        "query": query,
        "workers": args.workers,
        "selected_engines": len(records),
        "returned_count": len(results),
        "matched_count": len(matched),
        "wall_seconds": wall,
        "timing": timed(records),
        "counts": dict(Counter("success" if item["ok"] and item["count"] else "empty" if item["ok"] else "failed" for item in records)),
        "matched": matched,
        "results": results,
        "engines": [{key: value for key, value in record.items() if key != "results"} for record in records],
    }


def child(root, config, command, timeout):
    process = subprocess.Popen([sys.executable, "-I", str(root / "scripts/searxng_cli.py"), "--root", str(root), "--config", str(config), *command], cwd=root / "scripts", env=environment(root, config), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    from threading import Timer
    expired = []
    def expire():
        expired.append(True)
        process.kill()
    timer = Timer(timeout, expire)
    timer.start()
    stdout, stderr = process.communicate()
    timer.cancel()
    timed_out = bool(expired)
    error = redact(stderr.decode("utf-8"), config)
    def clean(value):
        if isinstance(value, str):
            return redact(value, config)
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    data = clean(json.loads(stdout.decode("utf-8"))) if process.returncode == 0 else None
    text = dump(data) if data is not None else redact(stdout.decode("utf-8"), config)
    return {"exitcode": process.returncode, "timed_out": timed_out, "stdout": text, "stderr": error, "data": data}


def add_search(parser):
    parser.add_argument("engine")
    parser.add_argument("query")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    parser.add_argument("--safesearch", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--category")
    parser.add_argument("--timeout", type=float, default=30)


def main():
    parser = argparse.ArgumentParser(description="独立调用原始 SearXNG 配置实例，无需启动 Web 服务")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, help="新建证据目录，禁止覆盖")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    commands.add_parser("schema")
    info = commands.add_parser("info")
    info.add_argument("engine")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--engines", nargs="+")
    doctor.add_argument("--initialize", action="store_true", help="显式允许 setup/init 及其外部请求")
    doctor.add_argument("--timeout", type=float, default=20)
    doctor.add_argument("--workers", type=int, default=4)
    add_search(commands.add_parser("search"))
    add_search(commands.add_parser("_search"))
    parallel = commands.add_parser("parallel")
    parallel.add_argument("--engines", nargs="+")
    parallel.add_argument("query")
    parallel.add_argument("--workers", type=int, default=4)
    parallel.add_argument("--page", type=int, default=1)
    parallel.add_argument("--language", default="en-US")
    parallel.add_argument("--time-range", choices=["day", "week", "month", "year"])
    parallel.add_argument("--safesearch", type=int, choices=[0, 1, 2], default=0)
    parallel.add_argument("--category")
    parallel.add_argument("--timeout", type=float, default=30)
    parallel.add_argument("--profile", choices=["general", "fashion", "fashion-images", "fashion-videos"])
    parallel.add_argument("--terms", nargs="+", help="筛选词；默认使用查询本身。标题、摘要或 URL 含任一筛选词才计入 matched")
    probe_parser = commands.add_parser("_probe")
    probe_parser.add_argument("engine")
    probe_parser.add_argument("--initialize", action="store_true")
    batch = commands.add_parser("batch")
    selection = batch.add_mutually_exclusive_group(required=True)
    selection.add_argument("--engines", nargs="+")
    selection.add_argument("--category")
    selection.add_argument("--all", action="store_true")
    batch.add_argument("--query", help="省略时按处理器使用有效查询示例")
    batch.add_argument("--interval", type=float, default=5)
    batch.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    root = args.root.resolve()
    config_path = (args.config or root / "scripts/settings.yml").resolve()
    if not config_path.is_relative_to(root):
        raise ValueError("配置文件必须位于项目根目录内")
    if args.output:
        args.output = args.output.resolve()
        if not args.output.is_relative_to(root):
            raise ValueError("输出目录必须位于项目根目录内")
        args.output.mkdir(parents=True, exist_ok=False)
    if hasattr(args, "timeout") and args.timeout <= 0:
        raise ValueError("timeout 必须大于零")
    if hasattr(args, "page") and args.page < 1:
        raise ValueError("page 必须大于零")
    searx = bootstrap(root, config_path)
    configs = {item["name"]: item for item in searx.settings["engines"]}
    if args.action.startswith("_"):
        config = configs[args.engine]
        result = probe(config, args.initialize) if args.action == "_probe" else search(config, args)
        print(dump(result))
        return 0
    entries = catalog(root, searx.settings)
    exitcode = 0
    if args.action == "schema":
        result = {"ok": True, "actions": ["list", "schema", "info", "doctor", "search", "parallel", "batch"], "global_options": ["--root", "--config", "--output"], "search": {"engine": "settings 实例名称", "query": "原始查询；字典如 en-de hello，货币如 10 USD to EUR，URL处理器需包含 URL", "page": "整数>=1", "language": "SearXNG locale", "time_range": [None, "day", "week", "month", "year"], "safesearch": [0, 1, 2], "category": "实例已声明的类别", "timeout": "正数秒，整个单渠道子进程另有10秒初始化余量"}, "parallel": {"engines": "至少两个 settings 实例名称", "workers": "并发子进程数，默认4", "result": "results 为合并后的结构化条目；engines 为每个实例的状态"}, "result": {"ok": "bool", "results": "原始 list/EngineResults 条目，typed Result 包含 result_type", "structured": "engine,result_type,title,url,content,published,thumbnail,authors", "empty_results": "成功但 count=0，批次单独记为空结果"}, "doctor": "默认实际导入、属性、traits检查，不调用setup/init；--initialize显式允许初始化外部依赖", "batch": "必须显式选择范围；逐实例串行；未选实例保存为unverified"}
    elif args.action in ("list", "info"):
        configured_modules = {item["engine_module"] for item in entries}
        module_files = sorted(path.stem for path in engine_dir().glob("*.py") if path.stem != "__init__")
        result = {"ok": True, "count": len(entries), "module_count": len(configured_modules), "source_module_count": len(module_files), "unconfigured_modules": [name for name in module_files if name not in configured_modules], "engines": entries if args.action == "list" else [next(item for item in entries if item["name"] == args.engine)]}
    elif args.action == "parallel":
        if not args.profile and not args.engines:
            raise ValueError("parallel 需要 --engines 或 --profile")
        if args.profile:
            names, profile_data = select_engines(root, args.profile)
            args.engines = names
            if not args.terms:
                args.terms = profile_data["terms"]
        unknown = [name for name in args.engines if name not in configs]
        if unknown:
            raise ValueError("未知实例：" + ", ".join(unknown))
        result = parallel_search(root, config_path, args.engines, args.query, args)
        exitcode = 0 if result["ok"] else 1
    elif args.action == "search":
        command = search_command(args.engine, args.query, args)
        record = child(root, config_path, command, args.timeout + 10)
        result = record["data"] if record["exitcode"] == 0 else {"ok": False, "engine": args.engine, **record}
        exitcode = 0 if result["ok"] else 1
        if record["stderr"]:
            print(record["stderr"], file=sys.stderr, end="")
    else:
        if args.action == "doctor":
            if args.workers < 1:
                raise ValueError("workers 必须大于零")
            names = args.engines or list(configs)
            def check(name):
                command = ["_probe", name] + (["--initialize"] if args.initialize else [])
                record = child(root, config_path, command, args.timeout)
                return {"engine": name, "status": record["data"]["status"] if record["data"] else "load_or_initialization_failed", **record}
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                records = list(executor.map(check, names))
            bad = {"configuration_missing", "inactive_or_tor_required", "unsupported_processor", "load_or_initialization_failed"}
            exitcode = int(any(item["status"] in bad for item in records))
        else:
            if args.interval < 1:
                raise ValueError("interval 必须至少为1秒")
            names = args.engines or [item["name"] for item in entries if args.all or args.category in item["categories"]]
            if not names:
                raise ValueError("选择范围没有配置实例")
            records = []
            for index, name in enumerate(names):
                if index:
                    time.sleep(args.interval)
                entry = next(item for item in entries if item["name"] == name)
                if entry["engine_module"] == "command" and not args.engines:
                    records.append({"engine": name, "status": "requires_explicit_engine_selection"})
                    continue
                query = args.query or EXAMPLE_QUERIES.get(entry["engine_type"], "Python")
                record = child(root, config_path, ["_search", name, query, "--timeout", str(args.timeout)], args.timeout + 10)
                status = "failed" if record["exitcode"] != 0 else ("success" if record["data"]["count"] else "empty")
                records.append({"engine": name, "status": status, **record})
                print(f"{index + 1}/{len(names)} {name}: {status}", file=sys.stderr, flush=True)
            exitcode = int(any(item["status"] != "success" for item in records))
        result = {"ok": exitcode == 0, "mode": args.action, "total_configurations": len(configs), "selected": len(records), "counts": dict(Counter(item["status"] for item in records)), "records": records, "unverified": [name for name in configs if name not in names]}
    if args.output:
        save(args.output / "report.json", result)
    print(dump(result))
    return exitcode


if __name__ == "__main__":
    sys.exit(main())
