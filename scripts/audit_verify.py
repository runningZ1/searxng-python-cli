# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from collections import Counter
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.is_relative_to(ROOT / 'results')
    rows = load(directory / 'all-352.json')
    catalog = load(ROOT / 'results/catalog-20261022/report.json')['engines']
    assert len(rows) == 352 and len({row['engine'] for row in rows}) == 352
    assert {row['engine'] for row in rows} == {row['name'] for row in catalog}
    previous = [row for row in rows if row.get('scope') == 'previous_7']
    current = [row for row in rows if row.get('scope') == 'current_345']
    assert len(previous) == 7 and len(current) == 345
    records = [load(path) for path in (directory / 'items').glob('*/record.json')]
    assert len({row['engine'] for row in records}) == len(records)
    evidence_summary = []
    invalid = []
    for row in records:
        evidence = ROOT / row['evidence']
        assert evidence.is_file() and evidence.is_relative_to(directory)
        if row['status'] == 'success':
            result_path = ROOT / row.get('results_evidence', str(evidence.parent.relative_to(ROOT) / 'stdout.json'))
            validation = subprocess.run([sys.executable, '-I', '-m', 'json.tool', str(result_path)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if validation.returncode:
                invalid.append({'engine': row['engine'], 'evidence': str(result_path.relative_to(ROOT)), 'error_type': 'JSONDecodeError'})
                continue
            data = load(result_path)
            assert data['ok'] is True and data['count'] > 0
            assert data['count'] == len(data['results']) == row['results_count']
            types = Counter(item.get('result_type', item.get('template', 'untyped')) for item in data['results'])
            object_counts = Counter()
            for item in data['results']:
                result_type = item.get('result_type', '').lower()
                if result_type in ('answer', 'translations', 'weatheranswer') or 'answer' in item:
                    object_counts['answer_count'] += 1
                elif result_type == 'suggestion' or 'suggestion' in item:
                    object_counts['suggestion_count'] += 1
                elif result_type == 'correction' or 'correction' in item:
                    object_counts['correction_count'] += 1
                elif result_type == 'infobox' or 'infobox' in item:
                    object_counts['infobox_count'] += 1
                else:
                    object_counts['search_result_count'] += 1
            public_urls = sum(isinstance(item.get('url'), str) and item['url'].startswith(('https://', 'http://')) for item in data['results'])
            evidence_summary.append({'engine': row['engine'], 'raw_result_count': data['count'], **{key: object_counts[key] for key in ('search_result_count', 'answer_count', 'suggestion_count', 'correction_count', 'infobox_count')}, 'result_types': dict(types), 'relevance': '未逐项核验' if row['engine'] != 'bpb' else '抽查未确认与Python查询的相关性', 'public_result_url_count': public_urls, 'evidence': str(result_path.relative_to(ROOT))})
        if row['status'] == 'blocked':
            assert row.get('blocked_reason')
        assert row.get('query') and row.get('started') and row.get('ended')
    if args.complete:
        assert len(records) == 345
        assert all(row['status'] != 'pending' for row in current)
        assert (directory / 'completed.json').exists()
    if (directory / 'classified-352.csv').exists():
        with (directory / 'classified-352.csv').open(encoding='utf-8-sig', newline='') as stream:
            csv_rows = list(csv.DictReader(stream))
        assert len(csv_rows) == 352
    (directory / 'invalid-evidence.json').write_text(json.dumps(invalid, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.complete:
        assert not invalid, invalid
    output = {'invalid_result_evidence': invalid, 'total': len(rows), 'current_scope': len(current), 'previous_scope': len(previous), 'completed_records': len(records), 'status_counts': dict(Counter(row['status'] for row in records)), 'successful_result_evidence': evidence_summary}
    (directory / 'verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in output.items() if key != 'successful_result_evidence'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
