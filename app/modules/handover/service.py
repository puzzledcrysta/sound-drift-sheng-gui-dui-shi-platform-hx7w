import json
from datetime import datetime, timezone
from time import perf_counter
from .manifest import handover_manifest
from .normalize import handover_intake
from .versions import inspect
from .timeline import map_timeline
from .planner import plan
from .reconcile import reconcile, confirmable
from .repository import persist, fetch


def _serializable(value):
    if isinstance(value, dict):
        return {k: _serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    return str(value) if value.__class__.__name__ == 'Decimal' else value


def build(source, book):
    raw = handover_intake(source)
    inspected = inspect(raw['passed'], raw['rejected_records'])
    ready, rejected = inspected['ready'], inspected['rejected']
    segments, domain_bad = map_timeline(ready)
    quarantine = sorted([*rejected, *domain_bad], key=lambda row: row['line'])
    items, gaps, stats = plan(segments)
    book_report = reconcile(items, book)
    gate = confirmable(book_report, quarantine, gaps)
    blank, repeated = len(raw['blank_lines']), len(raw['header_lines'])
    counts = {'input': raw['input_count'], 'accepted': len(ready),
              'quarantine': len(quarantine), 'suppressed': len(inspected['suppressed']),
              'blank': blank, 'repeated_header': repeated,
              'segments': len(segments),
              'handover_items': len([i for i in items if i['kind'] == '取用']),
              'gaps': len(gaps)}
    conserved = counts['input'] == (counts['accepted'] + counts['quarantine']
                                    + counts['suppressed'] + blank + repeated)
    if not conserved:
        raise RuntimeError('交接来源记录数量无法闭合')
    return {'segments': _serializable(segments), 'items': _serializable(items),
            'gaps': _serializable(gaps), 'stats': _serializable(stats),
            'book': book_report, 'gate': gate, 'counts': counts, 'balanced': conserved,
            'quarantine': quarantine, 'suppressed': inspected['suppressed'],
            'tracks': {role: [r['key'] for r in rows] for role, rows in inspected['tracks'].items()}}


def run(source, book):
    proof = handover_manifest(source, book)
    started = perf_counter()
    result = build(source, book)
    created = datetime.now(timezone.utc).isoformat()
    proof.update(elapsed_ms=round((perf_counter() - started) * 1000, 2), created=created)
    result['manifest'] = proof
    stored = persist(proof['run_id'], source, book, result, created)
    return json.loads(stored['result'])


def get(run_id):
    return json.loads(fetch(run_id)['result'])


def replay(run_id):
    old = fetch(run_id)
    return run(old['source'], old['book'])
