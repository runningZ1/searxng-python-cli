import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / 'results/catalog-20261022/report.json').read_text(encoding='utf-8'))
for engine in catalog['engines']:
    path = Path(engine['source_file'])
    tree = ast.parse(path.read_text(encoding='utf-8'))
    doc = (ast.get_docstring(tree) or '').replace('\n', ' ')[:220]
    print(json.dumps({'name': engine['name'], 'module': engine['engine_module'], 'description': doc}, ensure_ascii=False))
