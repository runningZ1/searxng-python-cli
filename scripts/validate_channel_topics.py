import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'重复 JSON 键：{key}')
        result[key] = value
    return result


catalog = json.loads((root / 'results/catalog-20261022/report.json').read_text(encoding='utf-8'))
data = json.loads((root / 'results/baseline-20261022/channel-topics.json').read_text(encoding='utf-8'), object_pairs_hook=unique_object)
expected = {item['name'] for item in catalog['engines']}
channels = data['channels']
assert len(expected) == len(channels) == data['instance_count'] == 352
assert set(channels) == expected, {'missing': sorted(expected - set(channels)), 'extra': sorted(set(channels) - expected)}
for name, entry in channels.items():
    assert entry['primary_topic'] in data['topics'], name
    for field in ('primary_topic', 'subtopic', 'retrieval_object', 'classification_basis'):
        assert isinstance(entry[field], str) and entry[field], (name, field)
    assert entry.get('confidence', data['defaults']['confidence']) in data['confidence_meaning'], name
    assert set(entry.get('secondary_topics', [])) <= set(data['topics']), name
print(json.dumps({'ok': True, 'count': len(channels), 'unique_keys': True, 'missing': [], 'extra': [], 'topics': dict(Counter(entry['primary_topic'] for entry in channels.values())), 'medium_confidence': [name for name, entry in channels.items() if entry.get('confidence') == 'medium']}, ensure_ascii=False, indent=2))
