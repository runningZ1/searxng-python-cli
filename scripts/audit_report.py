# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


OVERRIDES = {
    'openairepublications': ('学术论文', '学术文献索引', '论文'),
    'openairedatasets': ('科研数据', '开放科研数据', '数据集'),
    'pdbe': ('科研数据', '蛋白质结构', '蛋白质结构数据'),
    'openlibrary': ('图书与文献资源', '图书书目', '图书'),
    'goodreads': ('图书与文献资源', '图书书目与评论', '图书与读者评论'),
    'annas archive': ('图书与文献资源', '文献资源目录', '图书及文献'),
    'library genesis': ('图书与文献资源', '文献资源目录', '图书及文献'),
    'z-library': ('图书与文献资源', '文献资源目录', '图书及文献'),
    'bpb': ('知识与教育', '政治与历史', '政治历史知识'),
    'chefkoch': ('生活与饮食', '菜谱', '菜谱'),
    'emojipedia': ('知识与教育', 'Emoji', 'Emoji释义'),
    'ollama': ('编程与软件', '公开模型目录', '模型目录'),
    'wikinews': ('新闻', '协作新闻', '新闻报道'),
    'wikivoyage': ('旅行与地理', '旅行指南', '旅行知识'),
    'minecraft wiki': ('游戏', '游戏知识', '游戏知识'),
    'freesound': ('音乐与音频', '音效素材', '声音素材'),
    'cloudflareai': ('生成式服务', '生成式问答', '生成内容'),
    'azure': ('私人服务与资源', '云资源检索', '租户云资源'),
}
ACADEMIC = {'arxiv', 'crossref', 'semantic_scholar', 'google_scholar', 'pubmed', 'openalex', 'base', 'core', 'ads', 'hal', 'springer', 'openaire'}
DEVELOPMENT = {'github', 'gitlab', 'codeberg', 'sourcehut', 'bitbucket', 'gitea', 'pypi', 'npm', 'crates', 'docker', 'hex', 'huggingface', 'rubygems', 'metacpan', 'hoogle', 'mdn', 'libraries', 'pkg_go_dev', 'packagist'}
DOCS = {'arch linux wiki', 'nixos wiki', 'gentoo', 'gentoo wiki', 'mdn', 'microsoft learn', 'mankier', 'manpages'}
DISCUSS = {'stackoverflow', 'askubuntu', 'superuser', 'discuss.python', 'caddy.community', 'pi-hole.community'}
TECHNEWS = {'hackernews', 'habrahabr', 'lobste.rs'}
GENERAL = {'360search', 'baidu', 'bing', 'brave', 'duckduckgo', 'google', 'google_cse', 'mojeek', 'qwant', 'sogou', 'startpage', 'yahoo', 'yandex', 'yep', 'stract', 'mwmbl', 'wiby', 'presearch', 'marginalia'}


def enrich(row):
    name, module = row['engine'], row['engine_module']
    categories = row['upstream_categories']
    if isinstance(categories, str):
        categories = [part.strip() for part in categories.split(',')]
    row['upstream_categories'] = categories
    row.setdefault('query_options', {'safesearch': 0, 'page': 1, 'language': 'en-US', 'timeout': 35} if row.get('scope') == 'current_345' else {'evidence': '见此前原始报告，未重测'})
    category_themes = [('scientific publications', '学术论文', '学术文献索引', '论文'), ('packages', '编程与软件', '软件包仓库', '软件包'), ('repos', '编程与软件', '代码仓库', '代码仓库'), ('apps', '编程与软件', '应用商店', '软件应用'), ('software wikis', '编程与软件', '软件知识文档', '软件文档'), ('q&a', '编程与软件', '开发问答', '技术问答'), ('icons', '图片', '图标素材', '图标'), ('stock images', '图片', '摄影素材', '图片'), ('images', '图片', '图片搜索', '图片'), ('videos', '视频', '视频搜索', '视频'), ('music', '音乐与音频', '音乐与音频检索', '音乐或音频'), ('news', '新闻', '新闻检索', '新闻报道'), ('movies', '影视', '影视目录', '影视资料'), ('books', '图书与文献资源', '图书资源', '图书'), ('dictionaries', '词典与翻译', '词典', '词义'), ('translate', '词典与翻译', '翻译', '翻译'), ('weather', '天气', '天气查询', '天气'), ('map', '地图与地理', '地理地点', '地点'), ('shopping', '购物', '商品检索', '商品'), ('social media', '社区与社交', '社区内容', '社区内容'), ('files', '文件与资源', '文件检索', '文件'), ('it', '编程与软件', '开发技术', '技术资料'), ('onions', 'Tor网站', 'Tor网站搜索', 'Tor网站')]
    category_match = next(((theme, subtheme, obj) for category, theme, subtheme, obj in category_themes if category in categories), None)
    if name in OVERRIDES:
        theme, subtheme, obj = OVERRIDES[name]
    elif module in OVERRIDES:
        theme, subtheme, obj = OVERRIDES[module]
    elif name in DOCS:
        theme, subtheme, obj = '编程与软件', '技术文档', '开发文档'
    elif name in DISCUSS or module in {'stackoverflow', 'stackexchange'}:
        theme, subtheme, obj = '编程与软件', '开发问答与社区', '技术问答'
    elif name in TECHNEWS or module in TECHNEWS:
        theme, subtheme, obj = '科技资讯', '新闻与社区讨论', '科技报道与讨论'
    elif module in ACADEMIC:
        theme, subtheme, obj = '学术论文', '学术文献索引', '论文及学术文献'
    elif module in DEVELOPMENT or name in DEVELOPMENT:
        theme, subtheme, obj = '编程与软件', '代码、软件包及工具', '代码、软件包或软件工具'
    elif category_match:
        theme, subtheme, obj = category_match
    elif module in GENERAL or 'web' in categories:
        theme, subtheme, obj = '通用网页', '综合网页搜索', '网页'
    elif 'blogs' in categories:
        theme, subtheme, obj = '博客与独立网站', '博客及独立网站搜索', '博客文章或独立网页'
    elif module in {'wikipedia', 'wikidata', 'mediawiki', 'grokipedia', 'wikimini'} or name in {'ddg definitions', 'encyclosearch'}:
        theme, subtheme, obj = '知识与教育', '百科或知识库', '百科知识'
    elif module == 'destatis':
        theme, subtheme, obj = '统计数据', '官方统计资料', '统计数据'
    elif module in {'fyyd', 'podchaser'}:
        theme, subtheme, obj = '音乐与音频', '播客目录', '播客'
    elif module == 'steam':
        theme, subtheme, obj = '游戏', '游戏商店', '游戏'
    elif module in {'wolframalpha_noapi', 'wolframalpha_api'}:
        theme, subtheme, obj = '知识与计算', '计算知识查询', '计算结果与事实'
    elif module in {'repology'}:
        theme, subtheme, obj = '编程与软件', '软件包版本索引', '软件包'
    elif module in {'tineye'}:
        theme, subtheme, obj = '图片', '反向图片搜索', '图片来源'
    elif name == 'erowid':
        theme, subtheme, obj = '知识与教育', '精神活性物质资料', '专题资料'
    elif 'general' in categories:
        theme, subtheme, obj = '网页检索', '网站或网页搜索；独立索引关系未确认', '网页'
    elif row.get('theme') in ('通用或特定网站', '学术与科研'):
        theme, subtheme, obj = '用途未确认', '已有上游类别但缺少精确用途确认', '未确认'
    else:
        theme, subtheme, obj = row['theme'], row.get('subtheme', '未确认'), row.get('retrieval_object', '未确认')
    mapping_path = ROOT / 'results/baseline-20261022/channel-topics.json'
    if mapping_path.exists():
        mapping = load(mapping_path)
        topic = mapping['channels'].get(name)
        if topic:
            theme = topic['primary_topic']
            subtheme = topic['subtopic']
            obj = topic['retrieval_object']
            row['secondary_topics'] = topic.get('secondary_topics', [])
            row['classification_evidence'] = topic['classification_basis'] + '；' + row['source_evidence']
            row['classification_confidence'] = topic.get('confidence', mapping['defaults']['confidence'])
            row['classification_source'] = str(mapping_path.relative_to(ROOT))
    row.update(theme=theme, subtheme=subtheme, retrieval_object=obj)
    row.setdefault('classification_evidence', row['source_evidence'])
    if row['status'] == 'success' and row.get('scope') == 'current_345' and row['auth'] == 'config_unknown':
        row['auth_observation'] = '本次默认公开配置实测有结果；未读取用户凭据；长期认证要求未确认'
    else:
        row['auth_observation'] = '按静态声明、属性与本次执行证据判定'
    if module in ('mediawiki', 'gitlab', 'bing', 'lingva') and not row['auth_evidence']['credential_field_names']:
        row['auth'] = 'anonymous'
        row['auth_observation'] = '模块about声明无需API Key；公开默认实例endpoint'
    if module == 'github_code':
        row['auth'] = 'config_unknown'
        row['auth_observation'] = '上游默认Authorization placeholder路径；个人token可配置；本次未读取用户凭据'
    if module == 'discourse':
        row['auth'] = 'anonymous'
        row['auth_observation'] = '公开论坛匿名搜索；私人论坛可能需api_key及api_username'
    if module == 'libretranslate':
        row['auth_observation'] = '默认libretranslate.com明确需要API Key；其他自建端点是否需key由服务配置决定'
    if module == 'openalex':
        row['auth_observation'] = '公开Works API；mailto为可选联系信息'
    if module == 'pexels':
        row['auth'] = 'embedded_provider_key'
        row['auth_observation'] = 'embedded_provider_key：源码预置服务密钥及备用路径；来源和使用授权未确认，未发请求'
    if module == 'wolframalpha_api':
        row['auth_evidence_note'] = 'appid为必需应用密钥'
    if module in ('json_engine', 'xpath') and not row['auth_evidence']['credential_field_names']:
        row['auth_observation'] = '通用处理模块不声明服务认证政策；公开实例默认配置不含用户凭据，本次执行状态另列'
    row.setdefault('failure_category', None)
    if row['status'] == 'error':
        stderr_evidence = row.get('stderr_evidence')
        if stderr_evidence:
            import re
            stderr_text = (ROOT / stderr_evidence).read_text(encoding='utf-8')
            matches = re.findall(r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Timeout)):', stderr_text, flags=re.M)
            if matches:
                row['error_type'] = matches[-1]
        kind = row.get('error_type', '') or ''
        row['failure_category'] = 'access_denied' if 'AccessDenied' in kind or '401' in row.get('error_summary', '') or '403' in row.get('error_summary', '') else 'tls_error' if 'Certificate' in kind or 'SSLError' in kind else 'network_error' if 'Connection' in kind or 'DNSError' in kind or 'ProxyError' in kind else 'response_parse_error' if 'JSONDecode' in kind else 'upstream_or_configuration_error'
    elif row['status'] in ('timeout', 'rate_limited', 'captcha'):
        row['failure_category'] = row['status']
    elif row['status'] == 'blocked':
        row['failure_category'] = row.get('blocked_reason')
    if module == 'torznab':
        row['auth'] = 'private_backend'
        row['auth_observation'] = '需要真实Torznab endpoint；是否需API Key取决于服务端'
    if module == 'ahmia' and row.get('error_type') == 'RuntimeError':
        row['failure_category'] = 'tor_required_upstream_refused_loading'
    if module != 'ahmia' and row.get('error_type') == 'RuntimeError' and '上游拒绝加载' in row.get('error_summary', ''):
        row['failure_category'] = 'upstream_refused_loading_conditions_unmet'
    return row


def markdown_cell(value):
    return str(value if value is not None else '').replace('|', '\\|').replace('\n', ' ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.is_relative_to(ROOT / 'results')
    progress = load(directory / 'progress.json')
    rows = [enrich(row) for row in load(directory / 'all-352.json')]
    source_commit = load(directory / 'manifest.json')['source_commit']
    for row in rows:
        row['source_commit'] = source_commit
    assert len(rows) == 352 and len({row['engine'] for row in rows}) == 352
    assert sum(row.get('scope') == 'current_345' for row in rows) == 345
    assert sum(row.get('scope') == 'previous_7' for row in rows) == 7
    mapping_file = ROOT / 'results/baseline-20261022/channel-topics.json'
    if mapping_file.exists():
        assert set(load(mapping_file)['channels']) == {row['engine'] for row in rows}
    verification_path = directory / 'verification.json'
    if verification_path.exists():
        verified = {item['engine']: item for item in load(verification_path)['successful_result_evidence']}
        for row in rows:
            if row['engine'] in verified:
                row.update({key: value for key, value in verified[row['engine']].items() if key not in ('engine', 'evidence')})
                row['result_semantics'] = 'answer_success' if row.get('answer_count', 0) and not row.get('search_result_count', 0) else 'search_results'
    save(directory / 'classified-352.json', rows)
    current = [row for row in rows if row.get('scope') == 'current_345']
    save(directory / 'classification-counts.json', {scope: {'theme_counts': dict(Counter(row['theme'] for row in selected)), 'auth_counts': dict(Counter(row['auth'] for row in selected))} for scope, selected in [('current_345', current), ('all_352', rows)]})
    fields = ['engine', 'scope', 'source_commit', 'theme', 'subtheme', 'site', 'retrieval_object', 'upstream_categories', 'index_kind', 'auth', 'auth_observation', 'status', 'blocked_reason', 'query', 'query_options', 'results_count', 'raw_result_count', 'search_result_count', 'answer_count', 'suggestion_count', 'correction_count', 'infobox_count', 'result_semantics', 'relevance', 'error_type', 'failure_category', 'source_group', 'source_hosts', 'search_process_started', 'network_request_confirmed', 'started', 'ended', 'evidence', 'source_evidence', 'classification_evidence', 'classification_confidence', 'classification_source']
    with (directory / 'classified-352.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    manifest = load(directory / 'manifest.json')
    lines = ['# 默认 SearXNG 实例全量审计', '', f"本次队列共345个实例，已完成{progress['completed']}个，待处理{progress['remaining']}个。此前7个实例保留已有证据，总表共352个实例。", '', f"源代码 commit：`{manifest['source_commit']}`。开始时间：UTC {manifest['started']['utc']}；本地 {manifest['started']['local']}。", '']
    if (directory / 'completed.json').exists():
        completed = load(directory / 'completed.json')
        lines += [f"结束时间：UTC {completed['ended']['utc']}；本地 {completed['ended']['local']}。", '']
    status_names = {'success': '执行有结果', 'empty': '执行零条', 'error': '执行错误', 'timeout': '超时', 'blocked': '条件不足或同源保护', 'rate_limited': '源站限流', 'captcha': '源站验证码', 'pending': '等待执行'}
    status_text = '，'.join(f'{status_names.get(status, status)}{count}个' for status, count in Counter(row['status'] for row in current).items())
    lines += [f"本次状态：{status_text}。启动真实搜索子进程{progress['search_processes_started']}个；有明确网络执行证据{progress['network_confirmed']}个；未启动搜索子进程{progress['blocked_without_search_process']}个。", '', '搜索子进程数包含初始化或配置阶段失败；网络证据数量依据真实返回和网络错误识别。timeout无法证明请求已发出。空结果仅表示解析返回零条，未列入可用清单。结果数量是上游原始条目数，包含答案、建议等对象，可能存在重复；不代表独立文档数量。currency属于换算答案。相关性没有逐项核验，bpb抽查尚未确认与Python查询相关。', '', '## 按主题列出无需用户 API Key 的实测结果渠道', '']
    invalid_evidence_path = directory / 'invalid-evidence.json'
    invalid_names = {item['engine'] for item in load(invalid_evidence_path)} if invalid_evidence_path.exists() else set()
    usable = defaultdict(list)
    for row in rows:
        if row['status'] == 'success' and row['engine'] not in invalid_names and row['auth'] in ('anonymous', 'optional_api_key', 'config_unknown'):
            usable[row['theme']].append(row)
    usable_summary = {theme: {'count': len(entries), 'engines': [row['engine'] for row in entries]} for theme, entries in sorted(usable.items())}
    save(directory / 'available-by-topic.json', usable_summary)
    lines += [f"合并此前证据后，当前有{sum(len(entries) for entries in usable.values())}个实例在未提供用户密钥的配置下返回结果，分布于{len(usable)}个主题。", '']
    for theme, entries in sorted(usable.items()):
        lines += [f'### {theme}', '', '| 实例 | 认证类型 | 结果数量 | 证据 |', '| --- | --- | ---: | --- |']
        for row in entries:
            auth_label = '未提供用户密钥实测有结果；认证政策未确认' if row['auth'] == 'config_unknown' else row['auth']
            lines.append(f"| {markdown_cell(row['engine'])} | {auth_label} | {row.get('results_count', '')} | {row.get('evidence', '')} |")
        lines.append('')
    lines += ['未提供用户密钥实测有结果但认证政策未确认的渠道，已在认证列明确标注。长期凭据要求应以对应服务的正式政策为准。', '']
    for title, auth in [('需要 API Key 的实例', 'required_api_key'), ('API Key 可选的实例', 'optional_api_key'), ('无需 API Key 但需要其他凭据的实例', 'no_key_but_other_credentials'), ('私人后端的实例', 'private_backend'), ('认证要求未确认的实例', 'config_unknown'), ('上游预置服务密钥的实例', 'embedded_provider_key')]:
        lines += [f'## {title}', '', '| 主题 | 实例 | 状态 | 条件与认证说明 | 证据 |', '| --- | --- | --- | --- | --- |']
        for row in rows:
            if row['auth'] == auth:
                condition = row.get('blocked_reason', '') + '；' + row.get('auth_observation', '')
                lines.append(f"| {row['theme']} | {markdown_cell(row['engine'])} | {row['status']} | {markdown_cell(condition)} | {row.get('evidence', '')} |")
        lines.append('')
    lines += ['## 失败与未请求原因', '', '| 状态 | 数量 |', '| --- | ---: |']
    for status, count in sorted(Counter(row['status'] for row in current).items()):
        lines.append(f'| {status_names.get(status, status)}（{status}） | {count} |')
    reason_names = {'inactive_or_tor_required': '默认inactive或缺少Tor条件', 'missing_api_key_no_credentials_read': '缺少必需API Key，未读取凭据', 'missing_other_credentials_no_credentials_read': '缺少其他用户凭据', 'private_backend_not_provisioned': '缺少私人后端', 'blocked_by_prior_rate_limit': '此前同源429保护', 'blocked_by_prior_source_restriction': '此前同源验证码或限流保护', 'source_group_stopped_after_429_or_captcha': '本次同源429或验证码后停止', 'generative_service_not_authorized_for_generation': '生成式服务不属于搜索请求范围', 'upstream_embedded_api_key_and_fallback_not_permitted': '预置第三方密钥来源和使用授权未确认'}
    lines += ['', '| 未请求原因 | 数量 |', '| --- | ---: |']
    for reason, count in sorted(Counter(row.get('blocked_reason', '') for row in current if row['status'] == 'blocked').items()):
        lines.append(f'| {reason_names.get(reason, reason)}（{reason}） | {count} |')
    failure_names = {'access_denied': '访问拒绝', 'tls_error': 'TLS证书或连接错误', 'network_error': '网络连接错误', 'response_parse_error': '响应解析错误', 'upstream_or_configuration_error': '上游执行或配置错误', 'tor_required_upstream_refused_loading': '缺少Tor条件，上游拒绝加载', 'upstream_refused_loading_conditions_unmet': '加载条件不足，上游拒绝加载', 'timeout': '请求或进程超时', 'rate_limited': '源站限流', 'captcha': '验证码或异常流量限制'}
    lines += ['', '| 失败类别 | 数量 |', '| --- | ---: |']
    for category, count in sorted(Counter(row.get('failure_category') or '未细分' for row in current if row['status'] in ('error', 'timeout', 'rate_limited', 'captcha')).items()):
        lines.append(f'| {failure_names.get(category, category)}（{category}） | {count} |')
    lines += ['', '## 执行与复核命令', '', '从项目根目录执行：', '', '```powershell', f'& ./venv/Scripts/python.exe -I ./scripts/full_audit.py --output ./{directory.relative_to(ROOT).as_posix()} --resume --interval 8 --timeout 35', f'& ./venv/Scripts/python.exe -I ./scripts/audit_verify.py ./{directory.relative_to(ROOT).as_posix()} --complete', f'& ./venv/Scripts/python.exe -I ./scripts/audit_report.py ./{directory.relative_to(ROOT).as_posix()}', '```', '', 'resume保留已有逐项记录；源站429和验证码保护根据既有记录恢复。脚本不解除inactive或配置缺失条件。', '', '## 认证与主题覆盖统计', '', '| 统计范围 | 分类 | 数量 |', '| --- | --- | ---: |']
    for scope_name, selected_rows in [('本次345实例', current), ('合并352实例', rows)]:
        for auth, count in sorted(Counter(row['auth'] for row in selected_rows).items()):
            lines.append(f'| {scope_name} | {auth} | {count} |')
    lines += ['', '| 主题 | 本次345实例 | 合并352实例 |', '| --- | ---: | ---: |']
    current_themes = Counter(row['theme'] for row in current)
    all_themes = Counter(row['theme'] for row in rows)
    for theme, count in sorted(all_themes.items()):
        lines.append(f'| {theme} | {current_themes[theme]} | {count} |')
    lines += ['', '同源保护使用公开源码顶层 endpoint、公开默认配置 URL、模块及已知服务主机变体进行保守分组。无法准确识别共享来源时，按模块或网站组保护；受保护实例没有再次发送搜索请求，其状态不代表远端已对该实例单独返回429或验证码。此前 arxiv 的429及近期 Brave、百度限制用于预置保护；Bing302按实际错误记录。初始化内部的多次网络调用由原始上游实现控制，实例之间至少间隔8秒。', '', '错误日志隐藏完整请求URL和明显凭据字段；结果文件保留公开检索链接。不保存原始响应正文、请求头或Cookie。没有读取用户现有凭据或私有配置，没有部署私人后端，没有解除inactive，没有绕过验证码，没有自动重试429。', '', '完整352项分类与状态见 `classified-352.csv`（UTF-8 BOM），本次345项按主题逐项记录见 `details-345.md`，逐项JSON位于 `items/NNN/record.json`。', '']
    (directory / 'report.zh-CN.md').write_text('\n'.join(lines), encoding='utf-8')
    detail = ['# 本次345个实例逐项记录', '']
    grouped = defaultdict(list)
    for row in current:
        grouped[row['theme']].append(row)
    for theme, entries in sorted(grouped.items()):
        detail += [f'## {theme}', '', '| 实例 | 子主题 | 认证 | 状态 | 数量 | 查询 | 条件或错误 | 证据 |', '| --- | --- | --- | --- | ---: | --- | --- | --- |']
        for row in entries:
            values = [row['engine'], row['subtheme'], row['auth'], row['status'], row.get('results_count'), row['query'], row.get('blocked_reason', row.get('error_type', '')), row.get('evidence', '')]
            detail.append('| ' + ' | '.join(markdown_cell(value) for value in values) + ' |')
        detail.append('')
    (directory / 'details-345.md').write_text('\n'.join(detail), encoding='utf-8')
    print(json.dumps(progress, ensure_ascii=False))


if __name__ == '__main__':
    main()
