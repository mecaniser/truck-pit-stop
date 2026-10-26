"""Validate passive response/DOM parity without network access or stored response bodies."""
import hashlib
import json
import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/New_York')


def row_identity(row):
    links = set(row['links'])
    if len(links) != 1:
        raise ValueError('Ambiguous provider')
    match = re.fullmatch(r'#/fleetview/vehicles/summary/([1-9][0-9]*)', next(iter(links)))
    if not match:
        raise ValueError('Invalid provider')
    text = row['cells'][1].split('\n')[0].strip()
    for pattern in ('%m/%d/%Y %I:%M %p', '%b %d, %Y, %I:%M %p'):
        try:
            local = datetime.strptime(text, pattern)
            break
        except ValueError:
            continue
    else:
        raise ValueError('Invalid rendered departure')
    if local.replace(tzinfo=ZONE, fold=0).utcoffset() != local.replace(tzinfo=ZONE, fold=1).utcoffset():
        raise ValueError('Ambiguous or nonexistent local departure')
    return [match[1], local.strftime('%Y-%m-%dT%H:%M')]


def identities_digest(rows):
    identities = [row_identity(row) for row in rows]
    encoded = [json.dumps(item, separators=(',', ':')) for item in identities]
    if len(set(encoded)) != len(encoded):
        raise ValueError('Duplicate rendered identity')
    identities = [identity for _, identity in sorted(zip(encoded, identities))]
    return hashlib.sha256(json.dumps(identities, separators=(',', ':')).encode()).hexdigest()


def valid_populated_proof(window):
    try:
        p = window['populated_proof']
        rows = window['rows']
        first, last, read = [datetime.fromisoformat(x.replace('Z', '+00:00')) for x in
                             (p['first_observed_at'], p['last_observed_at'], window['source_read_at'])]
        integer_fields = ('version', 'total', 'per_page', 'response_count', 'response_identity_count', 'dom_identity_count')
        return (all(type(p[k]) is int for k in integer_fields)
                and p['version'] == 1 and p['kind'] == 'passive_provider_pages'
                and str(UUID(p['epoch'])) == p['epoch']
                and p['origin'] == 'https://api.keeptruckin.com'
                and p['start'] == p['end'] == window['start'] == window['end']
                and all(row_identity(row)[1].startswith(p['start'] + 'T') for row in rows)
                and 0 < p['total'] == len(rows) == p['response_identity_count'] == p['dom_identity_count'] <= 20000
                and 0 < p['per_page'] <= 20000
                and (p['total'] + p['per_page'] - 1) // p['per_page'] <= p['response_count'] <= 400
                and p['identity_sha256'] == identities_digest(rows)
                and first.tzinfo is not None and last.tzinfo is not None and read.tzinfo is not None
                and first <= last == read and (last - first).total_seconds() <= 1800)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError):
        return False
