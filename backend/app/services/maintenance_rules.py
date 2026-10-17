"""Pure maintenance precision, evidence admission and independent due arithmetic."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from zoneinfo import ZoneInfo
from fastapi import HTTPException

METERS = ('odometer_miles', 'engine_hours')
EMPTY_TARGETS = {'due_on':None, 'odometer_miles':None, 'engine_hours':None}
MAXIMUM = {'odometer_miles':Decimal('99999999'), 'engine_hours':Decimal('10000000')}


def fail(code, message, status=409, **extra):
    raise HTTPException(status, {'code':code, 'message':message, **extra}, headers={'Cache-Control':'private, no-store'})


def utc(value):
    if isinstance(value, str):
        value=datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat() if value is not None else None


def decimal_text(value):
    return format(Decimal(str(value)), 'f')


def number(value, meter, *, manual=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result=Decimal(str(value))
        step=Decimal(1) if meter=='odometer_miles' else Decimal('.01')
        if not result.is_finite() or result<0 or result>MAXIMUM[meter] or (manual and result != result.quantize(step)):
            raise ValueError()
        return result, result.quantize(step, rounding=ROUND_FLOOR)
    except (InvalidOperation, TypeError, ValueError):
        fail('maintenance_invalid_reading','Use a supported non-negative actual reading.',422,field=meter)


def freshness(observed_at, observed_on, now, zone):
    if observed_at is None:
        if observed_on is None:
            return 'unknown'
        age=now.astimezone(ZoneInfo(zone)).date()-date.fromisoformat(str(observed_on))
        return 'fresh' if age.days==0 else 'stale'
    age=now-utc(observed_at)
    return 'fresh' if age<=timedelta(minutes=5) else 'delayed' if age<=timedelta(minutes=15) else 'stale'


def observation(value, meter, *, source, basis, observed_at=None, observed_on=None,
                precision=None, captured_at=None, source_id=None, as_of, zone,
                identity_matches=True, baseline=None):
    original,comparison=number(value,meter)
    observed=utc(observed_at) if observed_at else None
    if not identity_matches:
        admission='identity_mismatch'
    elif (source=='motive_api' and basis!='calibrated') or (source=='motive_dashboard_manual' and (meter!='odometer_miles' or basis!='dashboard_unspecified')):
        admission='unverified_basis'
    elif observed is None and (source!='service_evidence' or observed_on is None):
        admission='missing_time'
    elif observed and observed>as_of+timedelta(minutes=5):
        admission='missing_time'
    elif baseline is not None and comparison<Decimal(str(baseline)):
        admission='regression'
    elif observed and observed<as_of-timedelta(days=30):
        admission='stale'
    else:
        admission='accepted'
    return {'value':decimal_text(original),'comparison_value':decimal_text(comparison) if admission in {'accepted','stale'} else None,
            'unit':'mi' if meter=='odometer_miles' else 'h','source':source,'basis':basis,
            'observed_at':iso(observed),'observed_on':str(observed_on) if observed_on else None,
            'observed_precision':precision or ('second' if observed else 'date' if observed_on else 'unknown'),
            'captured_at':iso(captured_at),'source_id':str(source_id) if source_id is not None else None,
            'freshness':freshness(observed,observed_on,as_of,zone),'admission':admission}


def choose_observation(candidates, *, baseline_on=None, zone='UTC'):
    def stamp(row):
        if row['observed_at']:
            return utc(row['observed_at'])
        if row['observed_on']:
            # Only ranking uses the calendar day. Returned evidence retains date precision.
            return datetime.combine(date.fromisoformat(row['observed_on']),datetime.min.time(),ZoneInfo(zone)).astimezone(timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)
    eligible=[row for row in candidates if not baseline_on or (
        (utc(row['observed_at']).astimezone(ZoneInfo(zone)).date() if row['observed_at'] else date.fromisoformat(row['observed_on']) if row['observed_on'] else date.min)>=baseline_on)]
    if not eligible:
        return None
    accepted=[row for row in eligible if row['admission'] in {'accepted','stale','regression'}]
    return max(accepted or eligible,key=lambda row:(stamp(row),row['captured_at'] or '',row['source_id'] or ''))


def due(intervals, targets, readings, *, as_of, zone, legacy=False):
    day=as_of.astimezone(ZoneInfo(zone)).date()
    date_enabled=intervals['days'] is not None or (legacy and targets['due_on'] is not None)
    remaining_days=(date.fromisoformat(str(targets['due_on']))-day).days if date_enabled and targets['due_on'] is not None else None
    date_state='disabled' if not date_enabled else state(remaining_days)
    result={'state':'unknown','date':{'state':date_state,'target':targets['due_on'],'remaining_days':remaining_days},'needs_reading':[],'needs_baseline':[]}
    if date_enabled and targets['due_on'] is None:
        result['needs_baseline'].append('date')
    for meter,key,interval in [('odometer_miles','miles','miles'),('engine_hours','engine_hours','engine_hours')]:
        enabled=intervals[interval] is not None or (legacy and targets[meter] is not None)
        reading=readings.get(meter)
        remaining=None
        if enabled and targets[meter] is not None and reading and reading['comparison_value'] is not None:
            remaining=Decimal(str(targets[meter]))-Decimal(reading['comparison_value'])
        current='disabled' if not enabled else state(remaining)
        if current=='current' and reading and (reading['freshness'] in {'stale','unknown'} or reading['admission']!='accepted'):
            current='unknown'
        if enabled and (reading is None or remaining is None or current=='unknown'):
            result['needs_reading'].append(meter)
        if enabled and targets[meter] is None:
            result['needs_baseline'].append(meter)
        result[key]={'state':current,'target':targets[meter],
                     'remaining':int(remaining) if meter=='odometer_miles' and remaining is not None else decimal_text(remaining) if remaining is not None else None,
                     'reading':reading}
    states=[result[key]['state'] for key in ('date','miles','engine_hours')]
    result['state']=next((candidate for candidate in ('overdue','due','unknown') if candidate in states),'current' if 'current' in states else 'unknown')
    return result


def state(remaining):
    return 'unknown' if remaining is None else 'overdue' if remaining<0 else 'due' if remaining==0 else 'current'


def next_targets(intervals, performed_on, readings, *, legacy=False):
    """Unknown dimensions stay unknown; advancement caller requires all enabled meters."""
    result=dict(EMPTY_TARGETS);missing=[]
    if performed_on is None:
        return result,['date']
    performed=date.fromisoformat(str(performed_on))
    for meter,key in [('odometer_miles','miles'),('engine_hours','engine_hours')]:
        interval=intervals[key]
        if interval is None:
            continue
        reading=readings.get(meter)
        if not reading or reading.get('comparison_value') is None:
            missing.append(meter);continue
        total=Decimal(reading['comparison_value'])+Decimal(str(interval))
        _,total=number(total,meter,manual=True)
        result[meter]=int(total) if meter=='odometer_miles' else decimal_text(total)
    if intervals['days'] is not None:
        try:
            days=intervals['days']
            if legacy and intervals['miles'] is not None:
                days=int((Decimal(str(intervals['miles']))/Decimal(600)).to_integral_value(rounding='ROUND_CEILING'))
            target=performed+timedelta(days=days)
            if legacy:
                target+=timedelta(days=(5-target.weekday())%7)
            result['due_on']=target.isoformat()
        except (OverflowError, ValueError):
            fail('maintenance_invalid_input','The next due date exceeds the supported calendar.',422,field='due_on')
    return result,missing
