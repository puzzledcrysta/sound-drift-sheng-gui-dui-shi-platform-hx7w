from decimal import Decimal as D
from .ledger import handover_ledger
from .planner import usage


def reconcile(items, payload):
    expected = handover_ledger(payload)
    actual = usage(items)
    rows, matches = [], 0
    for identity in sorted(actual.keys() | expected.keys()):
        key, role = identity
        value = actual.get(identity)
        book, book_line = expected.get(identity, (None, None))
        delta = (value or D('0')) - (book or D('0'))
        reason = ('MISSING_BOOK' if book is None else 'MISSING_RESULT' if value is None
                  else 'AMOUNT_DELTA' if delta else 'MATCH')
        matches += reason == 'MATCH'
        rows.append({'key': key, 'track': role,
                     'amount': str(value) if value is not None else None,
                     'reference': str(book) if book is not None else None, 'delta': str(delta),
                     'book_line': book_line, 'code': reason})
    actual_total = sum(actual.values(), D('0'))
    book_total = sum((pair[0] for pair in expected.values()), D('0'))
    mismatched = len(rows) - matches
    return {'rows': rows, 'matched': matches, 'mismatched': mismatched,
            'actual': str(actual_total.quantize(D('0.001'))),
            'expected': str(book_total.quantize(D('0.001'))),
            'delta': str((actual_total - book_total).quantize(D('0.001')))}


def confirmable(book, quarantine, gaps):
    """差异未核清（仍有账差或隔离片段）前不得确认交接；空档需显式标出但不阻断。"""
    blockers = []
    if book['mismatched']:
        blockers.append('RECONCILE_OPEN')
    if quarantine:
        blockers.append('QUARANTINE_OPEN')
    return {'confirmable': not blockers, 'blockers': blockers,
            'gap_count': len(gaps), 'gap_total': str(sum((g['duration'] for g in gaps), D('0')).quantize(D('0.001')))}
