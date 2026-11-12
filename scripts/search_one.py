# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description="兼容单渠道入口，参数由正式 CLI 处理")
parser.add_argument("engine")
parser.add_argument("query")
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--config", type=Path)
args, extra = parser.parse_known_args()
root = args.root.resolve()
command = [sys.executable, "-I", str(root / "scripts/searxng_cli.py"), "--root", str(root), "--output", str(args.output)]
if args.config:
    command.extend(["--config", str(args.config)])
command.extend(["search", args.engine, args.query, *extra])
sys.exit(subprocess.run(command, cwd=root / "scripts").returncode)
