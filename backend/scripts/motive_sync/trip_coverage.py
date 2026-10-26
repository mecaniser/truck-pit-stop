"""Receipt-derived trip catchup planning; no database writes or inferred empty days."""
import hashlib
import json
from datetime import date, datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/New_York')
FLOOR = date(2026, 4, 1)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def day_closed(day, source_read_at):
    """Only source observation after the local day ends can close that day."""
    read = datetime.fromisoformat(source_read_at.replace('Z', '+00:00'))
    if read.tzinfo is None:
        raise ValueError('Source read must be timezone aware')
    end = datetime.combine(date.fromisoformat(day) + timedelta(days=1), time.min, ZONE)
    return read >= end


def mapping_digest(directory, mappings, memberships, missing):
    """Source presentation and SQL row order never change identity coverage."""
    groups = dict(directory=directory, mappings=mappings, memberships=memberships, missing=missing)
    return digest({name: sorted(rows, key=lambda row: (
        str(row.get('provider_vehicle_id', '')), str(row.get('vehicle_id', '')),
        str(row.get('membership_id', '')), digest(row))) for name, rows in groups.items()})


def scope(tenant, actor, company, label, baseline):
    baseline = date.fromisoformat(baseline)
    if baseline < FLOOR:
        raise ValueError('History baseline precedes supported source contract')
    return dict(tenant_id=str(tenant), actor_id=str(actor), company_id=company,
                company_label=label, timezone='America/New_York', baseline=baseline.isoformat())


def validate_plan(plan, expected, today):
    if plan.get('version') != 1 or plan.get('scope') != expected:
        raise ValueError('Trip plan scope mismatch')
    days = plan.get('days')
    if not isinstance(days, list) or not 1 <= len(days) <= 31 or len(set(days)) != len(days):
        raise ValueError('Trip plan requires unique bounded days')
    baseline = date.fromisoformat(expected['baseline'])
    if any(not baseline <= date.fromisoformat(day) <= today for day in days):
        raise ValueError('Trip plan outside baseline or future')
    return days


def private_read(path, root=None):
    path = Path(path)
    if root is not None:
        relative = path.relative_to(root)
        cursor = Path(root)
        for part in relative.parts[:-1]:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("Trip evidence directory is symlinked")
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size > 32*1024*1024:
        raise ValueError("Trip evidence must be bounded private regular files")
    return json.loads(path.read_text())


def verified_days(state, expected):
    """Rebuild index only from hash-bound, verified committed catchup receipts."""
    found = {}
    for path in sorted(Path(state).glob('*/????-??-??/receipt.json')):
        receipt = private_read(path, state)
        if receipt.get('stage') != 'verified' or receipt.get('committed') is not True:
            continue
        coverage = receipt.get('coverage')
        if not coverage or coverage.get('scope') != expected:
            continue
        source = private_read(path.with_name('source.json'), state)
        normalized = private_read(Path(str(path)+'.normalized.json'), state)
        plan = source.get('plan')
        if (receipt.get('mode') != 'commit' or source.get('complete') is not True or
            source.get('company_verified_before') is not True or source.get('company_verified_after') is not True or
            not plan or plan.get('scope') != expected or
            digest(source) != receipt.get('source_sha256') or
            digest(source) != normalized.get('source_sha256') or
            digest(normalized) != receipt.get('normalized_sha256') or
            normalized.get('coverage') != coverage or
            any(receipt.get(k) != expected[k] or normalized.get(k) != expected[k]
                for k in ('tenant_id', 'actor_id')) or
            normalized.get('company_id') != expected['company_id'] or
            normalized.get('company_label') != expected['company_label'] or
            receipt.get('readback_verified') != len(normalized['rows']) or
            receipt.get('replay_unchanged') != len(normalized['rows']) or
            len(receipt.get('rows', [])) != len(normalized['rows'])):
            raise ValueError('Trip coverage evidence mismatch')
        day = coverage['day']
        if [w['start'] for w in source['windows']] != [day] or any(w['end'] != day for w in source['windows']):
            raise ValueError('Trip coverage window mismatch')
        if day not in plan['days']:
            raise ValueError('Trip coverage outside plan')
        # Later observations supersede earlier provisional observations.
        if day not in found or receipt['verified_at'] > found[day]['verified_at']:
            found[day] = {**coverage, 'verified_at': receipt['verified_at']}
    if found:
        latest = max(found.values(), key=lambda item: item['verified_at'])['mapping_sha256']
        # A changed directory/VIN/membership invalidates former scope certification.
        # Keep evidence on disk; recapture days for the new mapping scope.
        found = {day: item for day, item in found.items() if item['mapping_sha256'] == latest}
    return found


def plan_days(expected, today, examined, limit=14, start=None, end=None):
    if not 3 <= limit <= 31:
        raise ValueError('Trip window limit must be 3..31')
    baseline = date.fromisoformat(expected['baseline'])
    if baseline > today:
        raise ValueError('Future history baseline')
    if start or end:
        if not start or not end:
            raise ValueError('Both backfill bounds required')
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if not baseline <= first <= last <= today or (last-first).days+1 > limit:
            raise ValueError('Backfill range outside bounded plan')
        days = [(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    else:
        recent = [(today-timedelta(days=i)).isoformat() for i in (2, 1, 0)
                  if today-timedelta(days=i) >= baseline]
        # Examined exclusions stay visible but do not monopolize the backlog.
        old = [(baseline+timedelta(days=i)).isoformat() for i in range((today-baseline).days)
               if (baseline+timedelta(days=i)).isoformat() not in examined
               and (baseline+timedelta(days=i)).isoformat() not in recent]
        days = old[:limit-len(recent)] + recent
        # Once unseen backlog drains, revisit oldest unresolved observations fairly.
        retry = sorted((v['verified_at'], d) for d, v in examined.items()
                       if v['status'] != 'verified' and d not in days and d < today.isoformat())
        days = [d for _, d in retry[:limit-len(days)]] + days
    return {'version': 1, 'scope': expected, 'days': days}


def summarize(expected, examined, today):
    cursor = date.fromisoformat(expected['baseline'])
    while cursor < today and examined.get(cursor.isoformat(), {}).get('status') == 'verified':
        cursor += timedelta(days=1)
    return {'baseline': expected['baseline'], 'complete_through':
            (cursor-timedelta(days=1)).isoformat() if cursor > date.fromisoformat(expected['baseline']) else None,
            'examined_days': len(examined), 'unresolved_days':
            sorted(d for d,v in examined.items() if v['status'] != 'verified')}
