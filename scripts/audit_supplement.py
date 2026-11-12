# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('full_audit', ROOT / 'scripts/full_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.is_relative_to(ROOT / 'results')
    assert (directory / 'completed.json').exists()
    audit.save(directory / 'supplement-started.json', {'started': audit.stamp()})
    all_rows, remaining = audit.build_plan()
    paths = {audit.load(path)['engine']: path for path in (directory / 'items').glob('*/record.json')}
    selected = []
    for row in remaining:
        record = audit.load(paths[row['engine']])
        if row['engine'] in ('baidu images', 'baidu kaifa') and record.get('blocked_reason') == 'blocked_by_prior_source_restriction':
            selected.append(row)
        if row['engine_module'] == 'discourse' and record.get('blocked_reason') == 'missing_other_credentials_no_credentials_read':
            selected.append(row)
        if record.get('error_type') == 'AttributeError' and 'as_dict' in record.get('error_summary', ''):
            selected.append(row)
        if row['engine_module'] == 'pdbe' and record['status'] == 'empty':
            row['query'] = 'hemoglobin'
            selected.append(row)
        if row['engine_module'] in ('open_meteo', 'wttr', 'duckduckgo_weather', 'photon', 'openstreetmap', 'apple_maps') and record['status'] in ('error', 'empty', 'timeout'):
            row['query'] = 'Berlin'
            selected.append(row)
    invalid_path = directory / 'invalid-evidence.json'
    if invalid_path.exists():
        invalid_names = {item['engine'] for item in audit.load(invalid_path)}
        selected.extend(row for row in remaining if row['engine'] in invalid_names and row not in selected)
    stopped = set()
    stopped_groups = set()
    for path in paths.values():
        record = audit.load(path)
        if record['status'] in ('rate_limited', 'captcha'):
            stopped.update(record.get('source_hosts', []))
            stopped_groups.add(record['source_group'])
    for row in remaining:
        record = audit.load(paths[row['engine']])
        if row['engine_module'] == 'wallhaven' and record['status'] in ('error', 'empty'):
            selected.append(row)
    selected = list({row['engine']: row for row in selected}.values())
    audit.save(directory / 'supplement-plan.json', [{'engine': row['engine'], 'query': row['query'], 'prior_evidence': str(paths[row['engine']].relative_to(ROOT))} for row in selected])
    for row in selected:
        host = {'baidu images': 'image.baidu.com', 'baidu kaifa': 'kaifa.baidu.com'}.get(row['engine'])
        if host:
            row.update(source_hosts=[host], source_group='host:' + host, site=[host])
        if set(row['source_hosts']) & stopped or row['source_group'] in stopped_groups:
            print(json.dumps({'engine': row['engine'], 'supplement_status': 'protected_source_not_retried'}, ensure_ascii=False), flush=True)
            continue
        item = paths[row['engine']].parent
        supplementary = item / 'supplement'
        supplementary.mkdir(exist_ok=False)
        prior_record = audit.load(paths[row['engine']])
        audit.save(supplementary / 'prior-record.json', prior_record)
        record = {**row, 'scope': 'current_345', 'started': audit.stamp(), 'evidence': str(paths[row['engine']].relative_to(ROOT))}
        time.sleep(8)
        if row['engine_module'] == 'wallhaven':
            command = [str(ROOT / 'venv/Scripts/python.exe'), '-I', str(ROOT / 'scripts/searxng_cli.py'), 'search', row['engine'], row['query'], '--safesearch', '2', '--timeout', '35']
            process = subprocess.run(command, cwd=ROOT / 'scripts', capture_output=True, timeout=60)
            output = process.stdout.decode('utf-8')
            error = audit.sanitize(process.stderr.decode('utf-8', errors='replace'))
            (supplementary / 'stderr.txt').write_text(error, encoding='utf-8')
            record.update(query_options={'safesearch': 2, 'page': 1, 'language': 'en-US'}, search_process_started=True, network_request_confirmed=False, results_count=None)
            if process.returncode == 0:
                data = json.loads(output)
                audit.save(supplementary / 'stdout.json', data)
                record.update(status='success' if data['count'] else 'empty', results_count=data['count'], network_request_confirmed=True, results_evidence=str((supplementary / 'stdout.json').relative_to(ROOT)))
            else:
                audit.save(supplementary / 'failure.json', json.loads(output))
                record.update(status='rate_limited' if '429' in error else 'captcha' if 'Captcha' in error else 'error', error_type=error.splitlines()[-1].split(':')[0] if error.splitlines() else 'ChildProcessError')
        else:
            record.update(audit.execute(row, supplementary, 35))
        record['ended'] = audit.stamp()
        record['prior_evidence'] = str((supplementary / 'prior-record.json').relative_to(ROOT))
        audit.save(paths[row['engine']], record)
        if record['status'] in ('rate_limited', 'captcha'):
            stopped.update(row['source_hosts'])
            stopped_groups.add(row['source_group'])
        print(json.dumps({'engine': row['engine'], 'status': record['status']}, ensure_ascii=False), flush=True)
    progress = audit.overview(directory, all_rows)
    audit.save(directory / 'completed.json', {'ended': audit.stamp(), **progress})
    subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/audit_report.py'), str(directory)], check=True)


if __name__ == '__main__':
    main()
