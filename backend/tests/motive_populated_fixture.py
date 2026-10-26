from datetime import datetime, timedelta
from scripts.motive_sync.trip_populated_proof import identities_digest


def prove(window):
    read = datetime.fromisoformat(window['source_read_at'].replace('Z', '+00:00'))
    window['populated_proof'] = dict(version=1, kind='passive_provider_pages',
        epoch='00000000-0000-4000-8000-000000000001', origin='https://api.keeptruckin.com',
        start=window['start'], end=window['end'], total=len(window['rows']), per_page=50,
        response_count=(len(window['rows'])+49)//50, response_identity_count=len(window['rows']),
        dom_identity_count=len(window['rows']), identity_sha256=identities_digest(window['rows']),
        first_observed_at=(read-timedelta(seconds=10)).isoformat(),last_observed_at=window['source_read_at'])
    return window
