import json
from base64 import b64encode
from fastapi import APIRouter, Response
from app.inputs import HandoverPaired, Review
from . import service
from .repository import fetch, history
from .decisions import decide, timeline

router = APIRouter()


@router.post('/api/handover')
def create(source: HandoverPaired):
    return service.run(source.raw(), source.ledger())


@router.get('/api/handover')
def list_runs():
    return history()


@router.get('/api/handover/{run_id}')
def detail(run_id: str):
    return service.get(run_id)


@router.post('/api/handover/{run_id}/replay')
def again(run_id: str):
    return service.replay(run_id)


@router.get('/api/handover/{run_id}/source')
def source_inputs(run_id: str):
    record = fetch(run_id)
    return {'data_base64': b64encode(record['source']).decode(),
            'book_base64': b64encode(record['book']).decode()}


@router.get('/api/handover/{run_id}/reviews')
def reviews(run_id: str):
    return timeline(run_id)


@router.post('/api/handover/{run_id}/reviews')
def commit(run_id: str, review: Review):
    return decide(run_id, review.version, review.decision, review.note)


@router.get('/api/handover/{run_id}/export')
def export(run_id: str):
    run = service.get(run_id)
    bundle = json.dumps({'manifest': run['manifest'], 'counts': run['counts'],
                         'stats': run['stats'], 'gate': run['gate'],
                         'segments': run['segments'], 'handover': run['items'],
                         'gaps': run['gaps'], 'reconciliation': run['book'],
                         'quarantine': run['quarantine'], 'suppressed': run['suppressed'],
                         'review': timeline(run_id)}, ensure_ascii=False, indent=2)
    return Response(bundle, media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="handover-{run_id}.json"'})
