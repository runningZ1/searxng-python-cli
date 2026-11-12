# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / "results" / datetime.datetime.now().strftime("batch-%Y%m%d-%H%M%S-%f")
command = [sys.executable, "-I", str(root / "scripts/searxng_cli.py"), "--output", str(output), "batch", *sys.argv[1:]]
sys.exit(subprocess.run(command, cwd=root / "scripts").returncode)
