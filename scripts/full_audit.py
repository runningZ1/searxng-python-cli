# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import ast
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = {'github', 'wikibooks', 'sogou', 'mdn', 'hoogle', 'arxiv', 'crossref'}
PRIOR_STOP = {'arxiv', 'brave', 'baidu'}
SECRET = re.compile(r'api.?key|token|password|secret|credential|authorization|cookie', re.I)


def stamp():
    now = dt.datetime.now().astimezone()
    return {'utc': now.astimezone(dt.timezone.utc).isoformat(), 'local': now.isoformat()}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sanitize(text):
    text = re.sub(r'https?://[^\s<>\"\']+', '[URL omitted]', text)
    text = re.sub(r'(?i)((?:api.?key|token|password|secret|authorization|cookie)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', text)
    return text


def source_info(entry):
    path = Path(entry['source_file'])
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text, filename=str(path))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    values[target.id] = node.value.value
    hosts = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not any(re.search(r'url|endpoint|host|website|base', name, re.I) for name in names):
            continue
        for literal in ast.walk(node.value):
            if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
                continue
            for url in re.findall(r'https?://[^\s<>\"\'`]+', literal.value):
                host = urlsplit(url).hostname
                if host and not any(char in host for char in '{}%'):
                    hosts.add(host.lower())
    return text, values, hosts


def classify(entry, diagnostic):
    text, values, hosts = source_info(entry)
    module = entry['engine_module']
    name = entry['name']
    lower = (name + ' ' + module).lower()
    categories = entry['categories']
    academic = ('arxiv', 'crossref', 'semantic_scholar', 'google_scholar', 'pubmed', 'openalex', 'base', 'core', 'ads', 'scanr', 'hal', 'springer')
    developer = ('github', 'gitlab', 'codeberg', 'sourcehut', 'pypi', 'npm', 'crates', 'pkg', 'packag', 'docker', 'hex', 'huggingface', 'rubygems', 'metacpan', 'hoogle', 'mdn', 'stackoverflow', 'askubuntu', 'superuser', 'stackexchange', 'manpage', 'libraries')
    if any(word in lower for word in academic) or 'science' in categories:
        theme, target = '学术与科研', '论文或科研资料（依网站用途）'
    elif any(word in lower for word in developer) or 'it' in categories:
        theme, target = '编程与软件', '代码、软件包或技术文档（依网站用途）'
    elif entry['engine_type'] == 'online_dictionary' or any(word in lower for word in ('translate', 'deepl', 'lingva', 'libretranslate')):
        theme, target = '词典与翻译', '词义或翻译'
    elif entry['engine_type'] == 'online_currency':
        theme, target = '金融与换算', '货币转换'
    else:
        mappings = [('images', '图片', '图片'), ('videos', '视频', '视频'), ('music', '音乐与音频', '音乐或音频'), ('news', '新闻', '新闻报道'), ('map', '地图与地理', '地点'), ('files', '文件与资源', '文件'), ('social media', '社区与社交', '社区内容')]
        found = next(((theme, target) for category, theme, target in mappings if category in categories), None)
        theme, target = found or ('通用或特定网站', '网页；具体用途待结合模块文档确认')
    missing = diagnostic.get('missing_required_attributes', [])
    credential_fields = sorted({field for field in [*values, *entry['configuration_fields'], *missing] if SECRET.search(field)})
    key_fields = [field for field in credential_fields if re.search(r'api.?key', field, re.I)]
    other_fields = [field for field in credential_fields if field not in key_fields]
    if entry['require_api_key'] is True or any(field in missing for field in key_fields):
        auth = 'required_api_key'
    elif other_fields and any(field in missing for field in other_fields):
        auth = 'no_key_but_other_credentials'
    elif key_fields:
        auth = 'optional_api_key' if re.search(r'optional|without.{0,25}(?:key|token)|if\s+(?:self\.)?(?:api_key|access_token)', text, re.I) else 'config_unknown'
    elif any(word in lower for word in ('elasticsearch', 'opensearch', 'searx', 'typesense', 'meilisearch', 'mwmbl private', 'localsearch')):
        auth = 'private_backend'
    elif entry['require_api_key'] is False:
        auth = 'anonymous'
    else:
        auth = 'config_unknown'
    if module in ('google_cse', 'google', 'google_images', 'google_news', 'google_videos', 'duckduckgo', 'duckduckgo_extra', 'github', 'github_code', 'ollama'):
        auth = 'anonymous'
    if module == 'wolframalpha_api':
        auth = 'required_api_key'
    if module == 'libretranslate':
        auth = 'required_api_key'
    if module == 'azure':
        auth = 'no_key_but_other_credentials'
    if module == 'discourse':
        auth = 'anonymous'
    query = {'online_dictionary': 'en-de hello', 'online_currency': '10 USD to EUR', 'online_url_search': 'https://www.python.org/'}.get(entry['engine_type'], 'graph neural networks' if theme == '学术与科研' else 'python')
    if module in ('open_meteo', 'wttr', 'duckduckgo_weather', 'photon', 'openstreetmap', 'apple_maps'):
        query = 'Berlin'
    if module == 'pdbe':
        query = 'hemoglobin'
    return {'engine': name, 'engine_module': module, 'theme': theme, 'subtheme': '未确认', 'site': sorted(hosts), 'retrieval_object': target, 'upstream_categories': categories, 'index_kind': '未确认', 'auth': auth, 'auth_evidence': {'declared_require_api_key': entry['require_api_key'], 'credential_field_names': credential_fields, 'missing_attribute_names': missing, 'setup': entry['has_setup'], 'init': entry['has_init'], 'source_file': entry['source_file']}, 'query': query, 'disabled': entry['disabled'], 'inactive': diagnostic.get('inactive', entry['inactive']), 'source_hosts': sorted(hosts), 'source_group': module, 'diagnostic_status': diagnostic.get('status'), 'source_evidence': entry['source_file']}


def build_plan():
    catalog = load(ROOT / 'results/catalog-20261022/report.json')
    doctor = load(ROOT / 'results/doctor-20261022/report.json')
    diagnostics = {r['engine']: r['data'] for r in doctor['records']}
    rows = [classify(entry, diagnostics[entry['name']]) for entry in catalog['engines']]
    import yaml
    import searx
    public_settings = yaml.safe_load((Path(searx.__file__).resolve().parent / 'settings.yml').read_text(encoding='utf-8'))
    settings_by_name = {item['name']: item for item in public_settings['engines']}
    for row in rows:
        for field, value in settings_by_name[row['engine']].items():
            if isinstance(value, str) and re.search(r'url|endpoint|host', field, re.I) and value.startswith(('https://', 'http://')):
                host = urlsplit(value).hostname
                if host and not any(char in host for char in '{}%'):
                    row['source_hosts'].append(host.lower())
        row['source_hosts'] = sorted(set(row['source_hosts']))
        row['site'] = row['source_hosts']
        endpoints = [value for field, value in settings_by_name[row['engine']].items() if isinstance(value, str) and re.search(r'url|endpoint|host', field, re.I) and value.startswith(('https://', 'http://'))]
        row['configured_endpoint_hosts'] = sorted({urlsplit(value).hostname for value in endpoints if urlsplit(value).hostname})
    assert len(rows) == 352 and len({r['engine'] for r in rows}) == 352
    assert PREVIOUS <= {r['engine'] for r in rows}
    # 对公共网站主机和模块使用保守联合分组，不推断公共后缀。
    parent = {r['engine_module']: r['engine_module'] for r in rows}
    def root(module):
        while parent[module] != module:
            module = parent[module]
        return module
    owners = {}
    ignored = {'github.com', 'www.github.com', 'docs.searxng.org', 'en.wikipedia.org', 'www.w3.org', 'stackoverflow.com'}
    for row in rows:
        for host in row['source_hosts']:
            if host in ignored:
                continue
            # 已知网站的主机变体明确归入同一服务。
            group = next((brand for brand in ('google', 'bing', 'brave', 'baidu', 'arxiv', 'yahoo', 'yandex', 'duckduckgo', 'qwant', 'sogou', 'youtube', 'bilibili') if any(part == brand for part in host.split('.'))), host)
            if group in owners:
                parent[root(row['engine_module'])] = root(owners[group])
            owners[group] = row['engine_module']
    generic_modules = {'mediawiki', 'json_engine', 'xpath', 'html', 'discourse', 'lemmy', 'peertube', 'mastodon', 'searchmysite', 'gitea', 'sepiasearch'}
    for row in rows:
        if row['engine_module'] in generic_modules:
            row['source_group'] = 'host:' + (row['configured_endpoint_hosts'][0] if row['configured_endpoint_hosts'] else (row['source_hosts'][0] if row['source_hosts'] else row['engine']))
        else:
            row['source_group'] = root(row['engine_module'])
        if row['engine'] in ('baidu images', 'baidu kaifa'):
            host = 'image.baidu.com' if row['engine'] == 'baidu images' else 'kaifa.baidu.com'
            row.update(source_hosts=[host], source_group='host:' + host, site=[host])
    remaining = [r for r in rows if r['engine'] not in PREVIOUS]
    assert len(remaining) == 345
    return rows, remaining


def blocked_reason(row):
    lower = (row['engine'] + ' ' + row['engine_module']).lower()
    if row['engine_module'] == 'pexels':
        return 'upstream_embedded_api_key_and_fallback_not_permitted'
    if row['engine'] == 'baidu':
        return 'blocked_by_prior_source_restriction'
    if row['auth'] == 'required_api_key':
        return 'missing_api_key_no_credentials_read'
    if 'arxiv' in lower or row['engine_module'] == 'brave':
        return 'blocked_by_prior_rate_limit'
    if row['auth'] == 'no_key_but_other_credentials':
        return 'missing_other_credentials_no_credentials_read'
    if row['auth'] == 'private_backend':
        return 'private_backend_not_provisioned'
    if row['inactive']:
        return 'inactive_or_tor_required'
    if row['auth_evidence']['missing_attribute_names']:
        return 'missing_configuration:' + ','.join(row['auth_evidence']['missing_attribute_names'])
    if row['engine_module'] in ('cloudflareai', 'openai', 'gemini', 'anthropic', 'deepseek'):
        return 'generative_service_not_authorized_for_generation'
    return None


def execute(row, directory, timeout):
    safesearch = 2 if row['engine_module'] == 'wallhaven' else 0
    args = [str(ROOT / 'venv/Scripts/python.exe'), '-I', str(ROOT / 'scripts/searxng_cli.py'), '_search', row['engine'], row['query'], '--timeout', str(timeout), '--safesearch', str(safesearch)]
    stderr_path = directory / 'stderr.txt'
    stdout_path = directory / 'stdout.json'
    process = subprocess.Popen(args, cwd=ROOT / 'scripts', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    from threading import Timer
    expired = []
    def terminate():
        expired.append(True)
        process.kill()
    timer = Timer(timeout + 15, terminate)
    timer.start()
    stdout, stderr = process.communicate()
    timer.cancel()
    error = sanitize(stderr.decode('utf-8', errors='replace'))
    stderr_path.write_text(error, encoding='utf-8')
    output = stdout.decode('utf-8', errors='replace')
    result = {'process_exitcode': process.returncode, 'search_process_started': True, 'network_request_confirmed': False, 'stderr_evidence': str(stderr_path.relative_to(ROOT)), 'error_type': None, 'results_count': None}
    if expired:
        result.update(status='timeout', error_type='HardProcessTimeout')
    elif process.returncode:
        lines = [line for line in error.splitlines() if line.strip()]
        last = lines[-1] if lines else 'ChildProcessError'
        exception_types = re.findall(r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Timeout)):', error, flags=re.M)
        kind = exception_types[-1] if exception_types else last.split(':', 1)[0]
        status = 'rate_limited' if '429' in error or 'TooManyRequests' in error else 'captcha' if re.search(r'captcha|botdetected|bot detected|unusual traffic', error, re.I) else 'timeout' if re.search(r'timeout|timed out', kind, re.I) else 'error'
        result.update(status=status, error_type=kind, error_summary=last)
        result['network_request_confirmed'] = bool(re.search(r'HTTP|curl|requests|SearxEngineTooManyRequests|Captcha|CAPTCHA', error))
    else:
        data = json.loads(output)
        stdout_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        count = data['count']
        result.update(status='success' if count else 'empty', results_count=count, network_request_confirmed=True, results_evidence=str(stdout_path.relative_to(ROOT)))
    result['query_options'] = {'safesearch': safesearch, 'page': 1, 'language': 'en-US', 'timeout': timeout}
    return result


def overview(directory, all_rows):
    records = [load(path) for path in sorted((directory / 'items').glob('*/record.json'))]
    previous = load(ROOT / 'results/baseline-20261022/validation-summary.json')['network']
    by_name = {r['engine']: r for r in records}
    old = {r['engine']: r for r in previous}
    combined = []
    for row in all_rows:
        if row['engine'] in old:
            evidence = old[row['engine']]
            combined.append({**row, 'scope': 'previous_7', 'status': evidence['status'], 'results_count': evidence['count'], 'evidence': evidence['evidence']})
        elif row['engine'] in by_name:
            combined.append(by_name[row['engine']])
        else:
            combined.append({**row, 'scope': 'current_345', 'status': 'pending'})
    summary = {'updated': stamp(), 'total': 352, 'previous': 7, 'selected': 345, 'completed': len(records), 'remaining': 345-len(records), 'counts': dict(Counter(r['status'] for r in records)), 'search_processes_started': sum(r.get('search_process_started', False) for r in records), 'network_confirmed': sum(r.get('network_request_confirmed', False) for r in records), 'blocked_without_search_process': sum(not r.get('search_process_started', False) for r in records)}
    save(directory / 'progress.json', summary)
    save(directory / 'all-352.json', combined)
    fields = ['engine', 'scope', 'theme', 'subtheme', 'site', 'retrieval_object', 'upstream_categories', 'index_kind', 'auth', 'status', 'blocked_reason', 'query', 'results_count', 'error_type', 'source_group', 'source_hosts', 'search_process_started', 'network_request_confirmed', 'started', 'ended', 'evidence', 'source_evidence']
    with (directory / 'all-352.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in combined:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v for k,v in row.items()})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--interval', type=float, default=8)
    parser.add_argument('--timeout', type=float, default=35)
    args = parser.parse_args()
    assert args.interval >= 5 and args.timeout > 0
    directory = args.output.resolve()
    assert directory.is_relative_to(ROOT / 'results')
    directory.mkdir(exist_ok=args.resume)
    (directory / 'items').mkdir(exist_ok=args.resume)
    all_rows, remaining = build_plan()
    if not args.resume:
        save(directory / 'plan-352.json', all_rows)
        commit = subprocess.run(['git', '-C', str(ROOT / 'source'), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
        save(directory / 'manifest.json', {'started': stamp(), 'source_commit': commit, 'scope': 345, 'previous_preserved': sorted(PREVIOUS), 'interval_seconds': args.interval, 'hard_timeout_seconds': args.timeout + 15, 'source_group_method': '公开源码URL主机及模块保守联合；已知服务主机变体合并；不解析公共后缀。初始化内部请求由原始上游实现执行，实例之间串行限速。', 'credential_policy': '仅默认公开配置；不读取现有私有配置或环境凭据'})
    stopped = set()
    for path in (directory / 'items').glob('*/record.json'):
        record = load(path)
        if record['status'] in ('rate_limited', 'captcha'):
            stopped.add(record['source_group'])
    for row in all_rows:
        lower = (row['engine']+' '+row['engine_module']).lower()
        if row['engine'] == 'baidu' or 'arxiv' in lower or 'brave' in lower:
            stopped.add(row['source_group'])
    last_finished = 0.0
    for index, row in enumerate(remaining):
        item = directory / 'items' / f'{index+1:03d}'
        record_path = item / 'record.json'
        if record_path.exists():
            continue
        item.mkdir(exist_ok=True)
        reason = blocked_reason(row)
        if row['source_group'] in stopped and reason is None:
            reason = 'source_group_stopped_after_429_or_captcha'
        record = {**row, 'scope': 'current_345', 'started': stamp(), 'evidence': str(record_path.relative_to(ROOT)), 'search_process_started': False, 'network_request_confirmed': False, 'results_count': None, 'error_type': None}
        if reason:
            record.update(status='blocked', blocked_reason=reason)
        else:
            remaining_wait = args.interval - (time.monotonic() - last_finished)
            if remaining_wait > 0:
                time.sleep(remaining_wait)
            record.update(execute(row, item, args.timeout))
            last_finished = time.monotonic()
            if record['status'] in ('rate_limited', 'captcha'):
                stopped.add(row['source_group'])
        record['ended'] = stamp()
        save(record_path, record)
        progress = overview(directory, all_rows)
        print(json.dumps({'processed': progress['completed'], 'remaining': progress['remaining'], 'engine': row['engine'], 'status': record['status'], 'counts': progress['counts']}, ensure_ascii=False), flush=True)
    progress = overview(directory, all_rows)
    assert progress['completed'] == 345 and progress['remaining'] == 0
    save(directory / 'completed.json', {'ended': stamp(), **progress})


if __name__ == '__main__':
    main()
