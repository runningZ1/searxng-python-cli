# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
parser.add_argument('--target', type=int, required=True)
args = parser.parse_args()
directory = args.directory.resolve()
assert directory.is_relative_to(ROOT / 'results')
while True:
    progress_path = directory / 'progress.json'
    raw = progress_path.read_text(encoding='utf-8')
    if raw.strip().endswith('}'):
        progress = json.loads(raw)
        if progress['completed'] >= args.target or (directory / 'completed.json').exists():
            print(json.dumps(progress, ensure_ascii=False), flush=True)
            break
    time.sleep(10)
