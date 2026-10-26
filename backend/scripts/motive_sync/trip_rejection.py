"""Bounded preimport rejection evidence, deliberately separate from receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID
from scripts.motive_sync import trip_coverage

EXIT_CODE = 42
REASON = 'incomplete_prior_coverage'


class PriorCoverageMismatch(ValueError):
    def __init__(self, prior, covered, missing):
        self.counts = dict(prior=prior, covered=covered, missing=missing)
        self.source_sha256 = None
        super().__init__(f'{REASON}: prior={prior} covered={covered} missing={missing}')


def expected_scope():
    return trip_coverage.scope(os.environ['MOTIVE_SYNC_TENANT_ID'], os.environ['MOTIVE_SYNC_ACTOR_ID'],
        os.environ['MOTIVE_COMPANY_ID'], os.environ['MOTIVE_COMPANY_LABEL'],
        os.environ.get('MOTIVE_TRIPS_BASELINE', '2026-04-01'))


def source_binding(source_path, expected, *, rejected=False):
    source = Path(source_path)
    if source.name != 'source.json' or source.parent.is_symlink() or source.parent.parent.is_symlink():
        raise ValueError('Invalid daily source path')
    allowed = {'source.json', 'rejection.json'} if rejected else {'source.json'}
    if {p.name for p in source.parent.iterdir()} != allowed:
        raise ValueError('Prior attempt or unknown daily artifacts')
    document = trip_coverage.private_read(source)
    plan = document.get('plan', {})
    day = source.parent.name
    if (plan.get('scope') != expected or plan.get('version') != 1 or day not in plan.get('days', [])
        or len(document.get('windows', [])) != 1
        or document['windows'][0]['start'] != day or document['windows'][0]['end'] != day
        or document.get('company_id') != expected['company_id']
        or document.get('company_label') != expected['company_label']):
        raise ValueError('Daily rejection source scope mismatch')
    return {'scope': expected, 'day': day, 'run': source.parent.parent.name,
        'source_file_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}


def validate_counts(counts):
    if (not isinstance(counts, dict) or set(counts) != {'prior', 'covered', 'missing'}
        or any(type(value) is not int or value < 0 or value > 20000 for value in counts.values())
        or counts['missing'] < 1 or counts['covered'] + counts['missing'] != counts['prior']):
        raise ValueError('Invalid rejection counts')


def write_rejection(source_path, receipt_path, expected, nonce, mismatch):
    if Path(receipt_path) != Path(source_path).with_name('receipt.json'):
        raise ValueError('Rejection receipt path mismatch')
    UUID(nonce)
    binding = source_binding(source_path, expected)
    if trip_coverage.digest(trip_coverage.private_read(source_path)) != mismatch.source_sha256:
        raise ValueError('Rejected source changed after validation')
    validate_counts(mismatch.counts)
    value = {'version': 1, 'stage': 'preimport_rejected', 'reason': REASON,
        'committed': False, 'import_attempted': False, 'nonce': nonce,
        'observed_at': datetime.now(timezone.utc).isoformat(), **binding, 'counts': mismatch.counts}
    from scripts.motive_sync.trip_runner import immutable_json
    immutable_json(Path(source_path).with_name('rejection.json'), value)
    return value


def validate_rejection(source_path, expected, nonce, since):
    UUID(nonce)
    binding = source_binding(source_path, expected, rejected=True)
    value = trip_coverage.private_read(Path(source_path).with_name('rejection.json'))
    if (set(value) != {'version','stage','reason','committed','import_attempted','nonce','observed_at','scope','day','run','source_file_sha256','counts'}
        or value['version'] != 1 or value['stage'] != 'preimport_rejected' or value['reason'] != REASON
        or value['committed'] is not False or value['import_attempted'] is not False
        or value['nonce'] != nonce or any(value[key] != item for key,item in binding.items())):
        raise ValueError('Invalid rejection evidence')
    observed = datetime.fromisoformat(value['observed_at'])
    lower = datetime.fromisoformat(since)
    if observed.tzinfo is None or lower.tzinfo is None or not lower <= observed <= datetime.now(timezone.utc):
        raise ValueError('Stale rejection evidence')
    validate_counts(value['counts'])
    return {'day': value['day'], 'nonce': nonce, 'reason': REASON, 'counts': value['counts']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--since', required=True)
    args = parser.parse_args()
    try:
        result = validate_rejection(args.source, expected_scope(), args.nonce, args.since)
    except Exception:
        raise SystemExit('Rejection evidence invalid') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
