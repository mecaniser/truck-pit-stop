from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas.maintenance import ReadingCreate, Config, Attestation
from app.services import maintenance_rules as rules

NOW=datetime(2026,10,16,16,tzinfo=timezone.utc)
I={'days':30,'miles':10000,'engine_hours':'100.00'}
T={'due_on':'2026-10-16','odometer_miles':100000,'engine_hours':'1000.00'}


def reading(value,meter='odometer_miles',**kwargs):
    return rules.observation(value,meter,source='maintenance_manual',basis='staff_observed',observed_at=NOW,as_of=NOW,zone='America/New_York',**kwargs)


@pytest.mark.parametrize('value,expected',[(99999,'current'),(100000,'due'),(100001,'overdue')])
def test_exact_thresholds(value,expected):
    projection=rules.due({'days':None,'miles':10000,'engine_hours':None},T,{'odometer_miles':reading(value)},as_of=NOW,zone='America/New_York')
    assert projection['state']==expected
    assert projection['miles']['remaining']==100000-value


def test_known_overdue_wins_over_other_unknown_and_active_work_does_not_enter_calculation():
    result=rules.due(I,T,{'odometer_miles':reading(100001)},as_of=NOW,zone='America/New_York')
    assert result['state']=='overdue' and result['engine_hours']['state']=='unknown'
    assert result['needs_reading']==['engine_hours']


def test_unknown_is_not_zero_or_current():
    result=rules.due({'days':None,'miles':10,'engine_hours':None},T,{},as_of=NOW,zone='UTC')
    assert result['state']=='unknown' and result['miles']['remaining'] is None


@pytest.mark.parametrize('value,expected',[(100001,'overdue'),(100000,'due'),(99999,'unknown')])
def test_stale_evidence_only_proves_threshold_crossed(value,expected):
    old=reading(value);old.update(freshness='stale',admission='stale')
    assert rules.due({'days':None,'miles':10,'engine_hours':None},T,{'odometer_miles':old},as_of=NOW,zone='UTC')['state']==expected


@pytest.mark.parametrize('basis,meter,admission',[('virtual','engine_hours','unverified_basis'),('dashboard_unspecified','engine_hours','unverified_basis'),('dashboard_unspecified','odometer_miles','accepted')])
def test_provider_basis_is_not_promoted(basis,meter,admission):
    value=rules.observation('100',meter,source='motive_dashboard_manual' if basis=='dashboard_unspecified' else 'motive_api',basis=basis,observed_at=NOW,as_of=NOW,zone='UTC')
    assert value['admission']==admission
    assert (value['comparison_value'] is not None)==(admission=='accepted')


def test_captured_time_is_not_observed_time():
    value=rules.observation('100','odometer_miles',source='motive_api',basis='calibrated',captured_at=NOW,as_of=NOW,zone='UTC')
    assert value['admission']=='missing_time' and value['comparison_value'] is None


def test_original_provider_precision_is_preserved_alongside_domain_comparison():
    assert reading('100.999')['value']=='100.999'
    assert reading('100.999')['comparison_value']=='100'
    assert reading('100.999','engine_hours')['comparison_value']=='100.99'


def test_identity_and_regression_are_not_comparable():
    assert reading('100',identity_matches=False)['admission']=='identity_mismatch'
    assert reading('100',baseline=101)['admission']=='regression'


@pytest.mark.parametrize('value',[False,True,'NaN','Infinity','-1','100000000'])
def test_invalid_reading_never_becomes_zero(value):
    with pytest.raises(HTTPException) as exc:rules.number(value,'odometer_miles')
    assert exc.value.status_code==422


def test_service_date_precision_survives_without_fake_midnight():
    value=rules.observation('100','odometer_miles',source='service_evidence',basis='service_confirmed',observed_on='2026-10-16',as_of=NOW,zone='UTC')
    assert value['observed_at'] is None and value['observed_precision']=='date'
    assert value['observed_on']=='2026-10-16' and value['admission']=='accepted'


@pytest.mark.parametrize('stamp,expected',[('2026-11-01T03:59:00+00:00',1),('2026-11-01T04:01:00+00:00',0),('2026-11-01T07:00:00+00:00',0)])
def test_calendar_day_survives_midnight_and_dst(stamp,expected):
    result=rules.due({'days':1,'miles':None,'engine_hours':None},{'due_on':'2026-11-01','odometer_miles':None,'engine_hours':None},{},as_of=datetime.fromisoformat(stamp),zone='America/New_York')
    assert result['date']['remaining_days']==expected


def test_independent_targets_are_not_mileage_forecasts_or_saturdays():
    result,missing=rules.next_targets(I,'2026-10-16',{'odometer_miles':reading(90000),'engine_hours':reading('900','engine_hours')})
    assert result=={'due_on':'2026-11-15','odometer_miles':100000,'engine_hours':'1000.00'} and missing==[]
    no_date,_=rules.next_targets({'days':None,'miles':10000,'engine_hours':None},'2026-10-16',{'odometer_miles':reading(1)})
    assert no_date['due_on'] is None


def test_missing_meter_does_not_invent_baseline():
    targets,missing=rules.next_targets(I,'2026-10-16',{})
    assert targets['odometer_miles'] is targets['engine_hours'] is None
    assert missing==['odometer_miles','engine_hours']


def test_legacy_date_retains_600_mile_saturday_rule():
    targets,_=rules.next_targets(I,'2026-10-16',{'odometer_miles':reading(90000),'engine_hours':reading('900','engine_hours')},legacy=True)
    assert targets['due_on']=='2026-11-07'


def test_overflow_is_explicit():
    with pytest.raises(HTTPException):rules.next_targets(I,'2026-10-16',{'odometer_miles':reading(99999999)})
    with pytest.raises(HTTPException):rules.next_targets(I,'9999-12-31',{})


@pytest.mark.parametrize('field,value',[('odometer_miles',True),('odometer_miles','1'),('engine_hours',1),('engine_hours','NaN'),('observed_at','2026-10-16T12:00:00')])
def test_reading_wire_rejects_coercion(field,value):
    payload={'channel':'shop','observed_at':NOW.isoformat(),'odometer_miles':0,'engine_hours':None,'source':'staff_observed','note':None}
    payload[field]=value
    with pytest.raises(ValidationError):ReadingCreate.model_validate(payload)


def test_explicit_zero_and_decimal_string_accepted():
    payload={'channel':'shop','observed_at':NOW.isoformat(),'odometer_miles':0,'engine_hours':'0.00','source':'staff_observed','note':None}
    assert ReadingCreate.model_validate(payload).odometer_miles==0
    with pytest.raises(ValidationError):ReadingCreate.model_validate({**payload,'actor_id':'forged'})


def test_new_regression_is_not_hidden_by_older_accepted_baseline():
    from app.services.maintenance_rules import choose_observation
    baseline=rules.observation('500000','odometer_miles',source='service_evidence',basis='service_confirmed',observed_on='2026-10-15',as_of=NOW,zone='UTC')
    lower=rules.observation('200','odometer_miles',source='maintenance_manual',basis='staff_observed',observed_at=NOW,as_of=NOW,zone='UTC',baseline=500000)
    assert choose_observation([baseline,lower],baseline_on=date(2026,10,15))['admission']=='regression'
