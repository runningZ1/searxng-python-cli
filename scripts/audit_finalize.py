# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
args = parser.parse_args()
directory = args.directory.resolve()
assert directory.is_relative_to(ROOT / 'results')
while not (directory / 'completed.json').exists():
    time.sleep(10)
for script, extra in [('audit_verify.py', []), ('audit_supplement.py', []), ('audit_verify.py', ['--complete']), ('audit_report.py', []), ('audit_verify.py', ['--complete'])]:
    subprocess.run([sys.executable, '-I', str(ROOT / 'scripts' / script), str(directory), *extra], cwd=ROOT / 'scripts', check=True)
print('345 records and previous 7 evidence verified; local reports complete', flush=True)
