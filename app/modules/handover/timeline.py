from decimal import Decimal as D
from app.errors import DataError
from app.evidence import finding
from app.settings import UNIT
from app.modules.domain.rule import calibrate


def map_timeline(records):
    """将采信记录投影到校准时钟，返回带校准起止的片段与校时隔离项。"""
    segments, domain_bad = [], []
    for record in records:
        try:
            clock = calibrate(record['fields'])
        except DataError as error:
            domain_bad.append(finding(record, error.code, str(error)))
            continue
        if clock['start'] >= clock['end']:
            domain_bad.append(finding(record, 'SOUND_COVERAGE', '校准时长非正，无法接入交接'))
            continue
        segments.append({'key': record['key'], 'track': record['track'], 'line': record['line'],
                         'revision': record['revision'], 'start': clock['start'], 'end': clock['end'],
                         'duration': clock['duration'], 'unit': UNIT,
                         'proof': [{'metric': label, 'value': str(value), 'unit': unit}
                                   for label, value, unit in clock['proof']]})
    return segments, domain_bad


def total(segments):
    return sum((item['duration'] for item in segments), D(0))
