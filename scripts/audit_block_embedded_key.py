# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import importlib.util
from pathlib import Path

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
    all_rows, remaining = audit.build_plan()
    index, row = next((index, row) for index, row in enumerate(remaining) if row['engine_module'] == 'pexels')
    item = directory / 'items' / f'{index+1:03d}'
    item.mkdir(exist_ok=False)
    record = {**row, 'scope': 'current_345', 'status': 'blocked', 'blocked_reason': 'upstream_embedded_api_key_and_fallback_not_permitted', 'search_process_started': False, 'network_request_confirmed': False, 'results_count': None, 'error_type': None, 'started': audit.stamp(), 'ended': audit.stamp(), 'evidence': str((item / 'record.json').relative_to(ROOT))}
    audit.save(item / 'record.json', record)
    print('Pexels recorded as blocked; no network request sent')


if __name__ == '__main__':
    main()
