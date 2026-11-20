import json
from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection
from .repository import lookup

TABLE = 'handover_reviews'


def timeline(run_id):
    with connection() as db:
        lookup(db, run_id)
        return list(map(dict, db.execute(
            f'SELECT version,decision,note,changed FROM {TABLE} WHERE run_id=? ORDER BY version DESC',
            (run_id,))))


def decide(run_id, version, decision, note):
    note = note.strip()
    if decision not in {'确认', '退回'}:
        raise DataError('REVIEW_DECISION', '复核结论无效')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = json.loads(lookup(db, run_id)['result'])
        current = db.execute(
            f'SELECT COALESCE(MAX(version),0) FROM {TABLE} WHERE run_id=?', (run_id,)).fetchone()[0]
        if current != version:
            raise DataError('STALE', '复核版本已过期，请刷新', 409)
        gate = run['gate']
        if decision == '确认' and not gate['confirmable']:
            raise DataError('HANDOVER_OPEN', '差异未核清，不能确认交接；请先处理隔离与外部账差异')
        if (run['book']['mismatched'] or run['quarantine'] or run['gaps'] or decision == '退回') and not note:
            raise DataError('REVIEW_NOTE', '有差异、隔离或空档时须填写复核意见')
        record = {'version': current + 1, 'decision': decision, 'note': note,
                  'changed': datetime.now(timezone.utc).isoformat()}
        db.execute(f'INSERT INTO {TABLE} VALUES (?,?,?,?,?)', (run_id, *record.values()))
        return record
