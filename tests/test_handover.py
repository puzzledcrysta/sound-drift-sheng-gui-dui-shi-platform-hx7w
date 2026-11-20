import csv
import io
from decimal import Decimal
from pathlib import Path
import pytest
from app import settings
from app.errors import DataError
from app.modules.handover.planner import plan, usage
from app.modules.handover import service
from app.settings import TRACK_MAIN, TRACK_BACKUP

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source():
    return (ROOT / 'sample_data/handover.csv').read_bytes()


@pytest.fixture
def book():
    return (ROOT / 'sample_data/handover_external.csv').read_bytes()


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'DB', tmp_path / 'handover.sqlite3')


def seg(key, track, start, end, line=2):
    """以毫秒整数构造校准时间轴上的片段（时长即毫秒）。"""
    q = Decimal('0.001')
    return {'key': key, 'track': track, 'line': line, 'revision': 1,
            'start': Decimal(start).quantize(q), 'end': Decimal(end).quantize(q),
            'duration': Decimal(end - start).quantize(q), 'unit': '毫秒', 'proof': []}


def test_overlap_keeps_single_route_and_prefers_main():
    segments = [seg('M1', TRACK_MAIN, 0, 100), seg('B1', TRACK_BACKUP, 50, 150)]
    items, gaps, stats = plan(segments)
    kinds = [(i['kind'], i['track'], i['key']) for i in items]
    # 重叠的 50–100 只留主轨一路，备轨只补主轨空档 100–150。
    assert kinds == [('取用', TRACK_MAIN, 'M1'), ('取用', TRACK_BACKUP, 'B1')]
    assert all(not i['overlap'] or i['track'] == TRACK_MAIN for i in items)
    assert stats['switches'] == 1 and stats['covered'] == Decimal('150.000')


def test_minimal_switch_then_maximize_main():
    # 0–50 只有主轨；50–100 主备重叠；100–150 只有备轨。
    # 重叠区选主或选备都只产生 1 次换声（持平），按规则多留主轨。
    segments = [seg('M1', TRACK_MAIN, 0, 100), seg('B1', TRACK_BACKUP, 50, 150)]
    items, _, stats = plan(segments)
    assert stats['switches'] == 1
    taken = usage(items)
    assert taken[('M1', TRACK_MAIN)] == Decimal('100.000')   # 重叠 50–100 留给主轨
    assert taken[('B1', TRACK_BACKUP)] == Decimal('50.000')   # 备轨只补独有空档
    order = [i['track'] for i in items]
    assert order == [TRACK_MAIN, TRACK_BACKUP]


def test_backup_only_span_avoids_pointless_switch():
    # 备轨全程覆盖、主轨仅在非独有区间闪现：保留主轨会增加换声，故不切回。
    segments = [seg('B', TRACK_BACKUP, 0, 300),
                seg('M1', TRACK_MAIN, 100, 150), seg('M2', TRACK_MAIN, 200, 250)]
    items, _, stats = plan(segments)
    assert stats['switches'] == 0
    assert {i['key'] for i in items} == {'B'}  # 主轨无独有内容，不为它反复换声


def test_gap_is_marked_and_breaks_continuity():
    segments = [seg('M1', TRACK_MAIN, 0, 100), seg('B1', TRACK_BACKUP, 150, 200)]
    items, gaps, stats = plan(segments)
    assert len(gaps) == 1 and gaps[0]['start'] == Decimal('100.000')
    assert gaps[0]['end'] == Decimal('150.000') and gaps[0]['duration'] == Decimal('50.000')
    gap_item = next(i for i in items if i['kind'] == '空档')
    assert gap_item['track'] is None
    # 空档两侧不产生换声计数。
    assert stats['switches'] == 0 and stats['gap'] == Decimal('50.000')


def test_each_track_unique_content_is_preserved():
    segments = [seg('M1', TRACK_MAIN, 0, 100), seg('B1', TRACK_BACKUP, 100, 200)]
    items, _, _ = plan(segments)
    assert {i['key'] for i in items} == {'M1', 'B1'}
    assert sum(usage(items).values()) == Decimal('200.000')


def test_usage_sums_only_taken_portions():
    segments = [seg('M1', TRACK_MAIN, 0, 100), seg('B1', TRACK_BACKUP, 50, 150)]
    taken = usage(plan(segments)[0])
    assert taken == {('M1', TRACK_MAIN): Decimal('100.000'),
                     ('B1', TRACK_BACKUP): Decimal('50.000')}


def test_end_to_end_sample(source, book):
    report = service.run(source, book)
    assert report['balanced'] is True
    assert report['gate']['confirmable'] is True and report['gate']['blockers'] == []
    assert report['stats']['switches'] == 4
    assert report['book']['mismatched'] == 0 and report['book']['delta'] == '0.000'
    # 记录闭合：5 条输入全部采信。
    assert report['counts']['input'] == 5 and report['counts']['accepted'] == 5
    # 两轨独有内容都在清单里。
    keys = {i['key'] for i in report['items'] if i['kind'] == '取用'}
    assert {'M1', 'M2', 'M3', 'B1', 'B2'} <= keys


def test_repeated_run_does_not_add_manifest(source, book):
    first = service.run(source, book)
    second = service.run(source, book)
    assert first == second
    from app.modules.handover.repository import history
    assert len(history()) == 1


def test_unreconciled_delta_blocks_confirmation(source):
    rows = list(csv.reader(io.StringIO(source.decode('utf-8-sig'))))
    ledger_rows = list(csv.reader(io.StringIO(
        (ROOT / 'sample_data/handover_external.csv').read_text(encoding='utf-8'))))
    # 把 M2 的外部取用改错，制造未核清差异。
    for row in ledger_rows[1:]:
        if row[0] == 'M2':
            row[2] = '999.000'
    bad_book = io.StringIO(newline='')
    csv.writer(bad_book).writerows(ledger_rows)
    report = service.run(source, bad_book.getvalue().encode())
    assert report['gate']['confirmable'] is False
    assert 'RECONCILE_OPEN' in report['gate']['blockers']
    with pytest.raises(DataError) as error:
        from app.modules.handover.decisions import decide
        decide(report['manifest']['run_id'], 0, '确认', '强行确认')
    assert error.value.code == 'HANDOVER_OPEN'


def test_quarantine_blocks_confirmation(book):
    rows = list(csv.reader(io.StringIO((ROOT / 'sample_data/handover.csv').read_text(encoding='utf-8-sig'))))
    header, body = rows[0], rows[1:]
    role_idx = header.index('轨道角色')
    bad = [r.copy() for r in body]
    bad[0][role_idx] = '第三轨'
    out = io.StringIO(newline='')
    csv.writer(out).writerows([header, *bad])
    report = service.run(out.getvalue().encode(), book)
    assert report['counts']['quarantine'] >= 1
    assert report['gate']['confirmable'] is False
    assert 'QUARANTINE_OPEN' in report['gate']['blockers']


def test_duplicate_external_key_rejected(source):
    text = (ROOT / 'sample_data/handover_external.csv').read_text(encoding='utf-8')
    rows = list(csv.reader(io.StringIO(text)))
    rows.append(rows[1])
    dup = io.StringIO(newline='')
    csv.writer(dup).writerows(rows)
    with pytest.raises(DataError) as error:
        service.run(source, dup.getvalue().encode())
    assert error.value.code == 'BOOK_CONFLICT'


def test_bad_external_header_rejected(source):
    with pytest.raises(DataError) as error:
        service.run(source, '声轨片段,外部取用(毫秒)\nM1,1\n'.encode())
    assert error.value.code == 'HEADER'
