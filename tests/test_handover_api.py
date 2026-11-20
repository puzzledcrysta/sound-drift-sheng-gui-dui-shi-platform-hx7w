import pytest
from fastapi.testclient import TestClient
from app import settings
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'DB', tmp_path / 'handover-api.sqlite3')
    with TestClient(app) as client:
        yield client


def test_handover_endpoint_builds_manifest(client):
    report = client.post('/api/handover', json={}).json()
    assert report['gate']['confirmable'] is True
    assert report['manifest']['version'] == 'handover-1.0'
    assert 'run_id' in report['manifest']


def test_handover_idempotent_over_http(client):
    first = client.post('/api/handover', json={}).json()
    second = client.post('/api/handover', json={}).json()
    assert first == second
    assert len(client.get('/api/handover').json()) == 1


def test_replay_returns_same_manifest(client):
    run_id = client.post('/api/handover', json={}).json()['manifest']['run_id']
    again = client.post(f'/api/handover/{run_id}/replay').json()
    assert again['manifest']['run_id'] == run_id
    assert len(client.get('/api/handover').json()) == 1


def test_confirm_review_flow_and_stale(client):
    run_id = client.post('/api/handover', json={}).json()['manifest']['run_id']
    ok = client.post(f'/api/handover/{run_id}/reviews',
                     json={'version': 0, 'decision': '确认', 'note': '交接与外部账一致'})
    assert ok.status_code == 200 and ok.json()['version'] == 1
    stale = client.post(f'/api/handover/{run_id}/reviews',
                        json={'version': 0, 'decision': '确认', 'note': '过期'})
    assert (stale.status_code, stale.json()['code']) == (409, 'STALE')


def test_gap_requires_note(client):
    # 删除 M3 制造空档与账差，确认时既被门控拦截，退回也须填意见。
    import csv, io
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    rows = list(csv.reader(io.StringIO((root / 'sample_data/handover.csv').read_text(encoding='utf-8-sig'))))
    rows = [rows[0]] + [r for r in rows[1:] if r[0] != 'M3']
    out = io.StringIO(newline='')
    csv.writer(out).writerows(rows)
    run_id = client.post('/api/handover', json={'data': out.getvalue()}).json()['manifest']['run_id']
    blank = client.post(f'/api/handover/{run_id}/reviews',
                        json={'version': 0, 'decision': '退回', 'note': '   '})
    assert (blank.status_code, blank.json()['code']) == (422, 'REVIEW_NOTE')


def test_export_carries_handover_evidence(client):
    run_id = client.post('/api/handover', json={}).json()['manifest']['run_id']
    bundle = client.get(f'/api/handover/{run_id}/export')
    assert bundle.status_code == 200 and 'attachment' in bundle.headers['content-disposition']
    payload = bundle.json()
    assert payload['manifest']['run_id'] == run_id
    assert payload['handover'] and payload['reconciliation']['mismatched'] == 0
    assert payload['gate']['confirmable'] is True


def test_source_roundtrip(client):
    from base64 import b64decode
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    run_id = client.post('/api/handover', json={}).json()['manifest']['run_id']
    restored = client.get(f'/api/handover/{run_id}/source').json()
    assert b64decode(restored['data_base64']) == (root / 'sample_data/handover.csv').read_bytes()


def test_unknown_run_404(client):
    response = client.get('/api/handover/nope')
    assert (response.status_code, response.json()['code']) == (404, 'RUN_UNKNOWN')
