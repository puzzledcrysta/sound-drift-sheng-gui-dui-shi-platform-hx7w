from hashlib import sha256
from app.settings import HANDOVER_RULE_VERSION


def handover_manifest(raw, book):
    source_hash, book_hash = sha256(raw).hexdigest(), sha256(book).hexdigest()
    run_id = sha256(f'{HANDOVER_RULE_VERSION}:{source_hash}:{book_hash}'.encode()).hexdigest()
    return {'run_id': run_id, 'source_sha256': source_hash, 'book_sha256': book_hash,
            'version': HANDOVER_RULE_VERSION, 'parameters': {'mode': '剪辑交接清单'}}
