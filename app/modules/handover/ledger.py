from app.errors import DataError
from app.settings import KEY, UNIT, TRACK_FIELD
from app.modules.domain.values import number
from app.modules.intake.reader import decode, records
from .schema import track

EXTERNAL_HEADER = [KEY, TRACK_FIELD, f'外部取用({UNIT})']


def handover_ledger(payload):
    text, _ = decode(payload)
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    if header != EXTERNAL_HEADER:
        raise DataError('HEADER', f'交接外部账表头须为 {",".join(EXTERNAL_HEADER)}')
    by_key = {}
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 3 or not row[0].strip():
            raise DataError('WIDTH', f'交接外部账第 {line} 行缺少业务键、轨道或计量')
        key, role_raw, amount_raw = (cell.strip() for cell in row)
        role = track(role_raw)
        identity = (key, role)
        if identity in by_key:
            raise DataError('BOOK_CONFLICT', f'交接外部账第 {line} 行重复业务键 {key}/{role}')
        by_key[identity] = (number(amount_raw), line)
    return by_key
