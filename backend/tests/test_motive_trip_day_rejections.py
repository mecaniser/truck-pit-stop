"""Only proven preimport day failures may leave later dates runnable."""
import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from scripts.motive_sync import trip_rejection as rejection, trip_coverage as coverage, trip_runner as runner
from tests.test_motive_trip_worker import source
from tests.test_db036_fleet_telemetry import prepared


def evidence(tmp_path, monkeypatch):
    expected=coverage.scope(str(uuid4()),str(uuid4()),'KT8934277','77 CARGO LLC','2026-04-01')
    for key,value in {'MOTIVE_SYNC_TENANT_ID':expected['tenant_id'],'MOTIVE_SYNC_ACTOR_ID':expected['actor_id'],'MOTIVE_COMPANY_ID':expected['company_id'],'MOTIVE_COMPANY_LABEL':expected['company_label']}.items():monkeypatch.setenv(key,value)
    document=source();day=document['windows'][0]['end'];document['windows'][0]['start']=day
    document['plan']={'version':1,'scope':expected,'days':[day]}
    path=tmp_path/'run'/day/'source.json';path.parent.mkdir(parents=True);path.touch(mode=0o600);path.write_text(json.dumps(document))
    nonce=str(uuid4());since=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    error=rejection.PriorCoverageMismatch(80,48,32);error.source_sha256=coverage.digest(document)
    return path,expected,nonce,since,error


def test_valid_rejection_is_not_receipt_or_coverage(tmp_path,monkeypatch):
    path,scope,nonce,since,error=evidence(tmp_path,monkeypatch)
    saved=rejection.write_rejection(path,path.with_name('receipt.json'),scope,nonce,error)
    assert saved['committed'] is False and saved['import_attempted'] is False
    assert rejection.validate_rejection(path,scope,nonce,since)['counts']==error.counts
    assert coverage.verified_days(tmp_path,scope)=={}
    assert not path.with_name('receipt.json').exists()
    assert coverage.summarize(scope,{},datetime.now(coverage.ZONE).date())['complete_through'] is None

@pytest.mark.parametrize('bad',['nonce','scope','day','run','source','stale','counts','attempted','extra','symlink'])
def test_invalid_rejection_never_authorizes_continue(tmp_path,monkeypatch,bad):
    path,scope,nonce,since,error=evidence(tmp_path,monkeypatch)
    rejection.write_rejection(path,path.with_name('receipt.json'),scope,nonce,error)
    target=path.with_name('rejection.json');value=json.loads(target.read_text())
    if bad=='nonce':value['nonce']=str(uuid4())
    if bad=='scope':value['scope']['tenant_id']=str(uuid4())
    if bad=='day':value['day']='2026-04-01'
    if bad=='run':value['run']='other'
    if bad=='source':path.write_text(path.read_text()+' ')
    if bad=='stale':value['observed_at']='2026-01-01T00:00:00+00:00'
    if bad=='counts':value['counts']['missing']=0
    if bad=='attempted':value['import_attempted']=True
    if bad=='extra':value['unknown']='PRIVATE'
    target.write_text(json.dumps(value))
    if bad=='symlink':target.rename(target.with_name('hidden.json'));target.symlink_to('hidden.json')
    with pytest.raises(ValueError):rejection.validate_rejection(path,scope,nonce,since)

@pytest.mark.parametrize('artifact',['receipt.json','receipt.json.normalized.json','attempt.json','unknown.json'])
def test_existing_attempt_blocks_write_and_validation(tmp_path,monkeypatch,artifact):
    path,scope,nonce,since,error=evidence(tmp_path,monkeypatch)
    marker=path.with_name(artifact);marker.touch(mode=0o600)
    with pytest.raises(ValueError,match='artifacts'):rejection.write_rejection(path,path.with_name('receipt.json'),scope,nonce,error)
    marker.unlink();rejection.write_rejection(path,path.with_name('receipt.json'),scope,nonce,error);marker.touch(mode=0o600)
    with pytest.raises(ValueError,match='artifacts'):rejection.validate_rejection(path,scope,nonce,since)


def test_changed_source_since_prepare_cannot_write_rejection(tmp_path,monkeypatch):
    path,scope,nonce,since,error=evidence(tmp_path,monkeypatch)
    document=json.loads(path.read_text());document['finished_at']=datetime.now(timezone.utc).isoformat();path.write_text(json.dumps(document))
    with pytest.raises(ValueError,match='changed after'):rejection.write_rejection(path,path.with_name('receipt.json'),scope,nonce,error)

@pytest.mark.asyncio
async def test_real_mismatch_rolls_back_before_import(_db_engine,db_session,monkeypatch,tmp_path):
    actor,_,member=await prepared(db_session,monkeypatch)
    member.effective_from=datetime.now(timezone.utc)-timedelta(days=7);await db_session.commit()
    factory=async_sessionmaker(_db_engine,expire_on_commit=False)
    original=source();args=(actor.tenant_id,actor.id,'77 CARGO LLC','KT8934277')
    await runner.run(factory,original,*args,tmp_path/'original.json',True)
    changed=copy.deepcopy(original);changed['windows'][0]['rows'][0]['cells'][1]=changed['windows'][0]['rows'][0]['cells'][1].replace('01:00 PM','03:00 PM')
    imports=AsyncMock(side_effect=AssertionError('Import attempted'))
    monkeypatch.setattr(runner,'import_batches',imports)
    rollback=AsyncMock();real=factory()
    original_rollback=real.rollback
    async def rolled():await rollback();await original_rollback()
    monkeypatch.setattr(real,'rollback',rolled)
    with pytest.raises(rejection.PriorCoverageMismatch) as caught:
        await runner.run(lambda:real,changed,*args,tmp_path/'rejected.json',True)
    rollback.assert_awaited_once();imports.assert_not_awaited()
    assert caught.value.source_sha256==coverage.digest(changed)
    assert not (tmp_path/'rejected.json').exists() and not (tmp_path/'rejected.json.normalized.json').exists()

@pytest.mark.parametrize('recover',[False,True])
def test_real_cli_only_converts_nonrecovery_typed_failure(tmp_path,monkeypatch,recover):
    path,scope,nonce,since,error=evidence(tmp_path,monkeypatch)
    async def mismatch(*args,**kwargs):raise error
    monkeypatch.setattr(runner,'recover' if recover else 'run',mismatch)
    import sys
    monkeypatch.setattr(sys,'argv',['runner','--input',str(path),'--receipt',str(path.with_name('receipt.json')),'--rejection-nonce',nonce,'--commit']+(['--recover'] if recover else []))
    if recover:
        with pytest.raises(rejection.PriorCoverageMismatch):runner.main()
        assert not path.with_name('rejection.json').exists()
    else:
        with pytest.raises(SystemExit) as exit:runner.main()
        assert exit.value.code==42
        assert rejection.validate_rejection(path,scope,nonce,since)['day']==path.parent.name

@pytest.mark.parametrize('bad',['none','exit_without_evidence','wrong_nonce','attempt_artifact','timeout'])
def test_real_node_python_rejection_boundary(tmp_path,monkeypatch,bad):
    import os,subprocess,sys
    path,scope,_,_,_=evidence(tmp_path,monkeypatch)
    # Run a fixture importer across the real Node wrapper and actual shared validator.
    package=tmp_path/'fixture'/'scripts'/'motive_sync';package.mkdir(parents=True)
    (package.parent/'__init__.py').write_text('');(package/'__init__.py').write_text('')
    import shutil
    for name in ('trip_coverage.py','trip_rejection.py'):shutil.copy(Path(rejection.__file__).with_name(name),package/name)
    (package/'trip_runner.py').write_text('''import argparse,json,os,time
from pathlib import Path
from scripts.motive_sync import trip_rejection as rejection,trip_coverage as coverage
def immutable_json(path,value):
    with open(path,'x') as out:json.dump(value,out)
    Path(path).chmod(0o600)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--receipt');p.add_argument('--commit',action='store_true');p.add_argument('--rejection-nonce');a=p.parse_args()
    document=json.loads(Path(a.input).read_text())
    if document['windows'][0]['start']=='2026-10-19':
        mode=os.environ['FIXTURE_MODE']
        if mode=='timeout':time.sleep(5)
        if mode=='exit_without_evidence':raise SystemExit(42)
        error=rejection.PriorCoverageMismatch(80,48,32);error.source_sha256=coverage.digest(document)
        rejection.write_rejection(a.input,a.receipt,rejection.expected_scope(),a.rejection_nonce,error)
        target=Path(a.input).with_name('rejection.json')
        if mode=='wrong_nonce':
            value=json.loads(target.read_text());value['nonce']='00000000-0000-0000-0000-000000000000';target.write_text(json.dumps(value))
        if mode=='attempt_artifact':Path(a.receipt+'.normalized.json').touch(mode=0o600)
        raise SystemExit(42)
    Path(a.receipt).write_text(json.dumps({'stage':'verified'}));Path(a.receipt).chmod(0o600)
''')
    run=tmp_path/'processrun';run.mkdir();collector=Path(runner.__file__).with_name('collect_trips.cjs')
    script=tmp_path/'process.cjs'
    plan={'version':1,'scope':scope,'days':['2026-10-19','2026-10-20']}
    result={'company_id':scope['company_id'],'company_label':scope['company_label']}
    script.write_text("const {importDay}=require("+json.dumps(str(collector))+");const output="+json.dumps(str(run/'source.json'))+";const plan="+json.dumps(plan)+";const result="+json.dumps(result)+";try {const a=importDay(output,result,plan,{start:'2026-10-19'},{start:'2026-10-19',end:'2026-10-19'},{timeout:1000});if(a.stage!=='preimport_rejected')throw Error('bad result');const b=importDay(output,result,plan,{start:'2026-10-20'},{start:'2026-10-20',end:'2026-10-20'});if(b.stage!=='verified')throw Error('bad second');process.stdout.write('continued');}catch(e){if(e.message!=='trip_import_failed')throw e;process.stdout.write('aborted');}")
    env={**os.environ,'MOTIVE_TRIPS_PYTHON':sys.executable,'MOTIVE_TRIPS_COMMIT':'true','PYTHONPATH':str(tmp_path/'fixture'),'FIXTURE_MODE':bad}
    completed=subprocess.run(['node',str(script)],env=env,cwd=tmp_path,text=True,capture_output=True,check=True,timeout=15)
    assert completed.stdout.endswith('continued' if bad=='none' else 'aborted')
    assert (run/'2026-10-20'/'receipt.json').exists() == (bad=='none')
    assert not (run/'2026-10-19'/'receipt.json').exists()


def test_worker_mixed_batch_reports_partial_without_accepting_rejection(tmp_path,monkeypatch,capsys):
    from scripts.motive_sync import run_trip_worker as worker
    _,scope,_,_,_=evidence(tmp_path/'unused',monkeypatch)
    monkeypatch.setenv('MOTIVE_TRIPS_STATE_DIR',str(tmp_path/'state'));monkeypatch.setenv('MOTIVE_TRIPS_COMMIT','true')
    monkeypatch.setenv('MOTIVE_TRIPS_FROM','2026-10-19');monkeypatch.setenv('MOTIVE_TRIPS_TO','2026-10-20')
    monkeypatch.setattr(coverage,'verified_days',lambda *args:{})
    def process(command,**kwargs):
        output=Path(command[-1]);plan=json.loads(Path(kwargs['env']['MOTIVE_TRIPS_PLAN_FILE']).read_text());started=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        rejected=[]
        for day in plan['days']:
            source_path=output.parent/day/'source.json';source_path.parent.mkdir()
            document={'company_id':scope['company_id'],'company_label':scope['company_label'],'plan':plan,'windows':[{'start':day,'end':day}]}
            runner.immutable_json(source_path,document)
            if day=='2026-10-19':
                nonce=str(uuid4());error=rejection.PriorCoverageMismatch(80,48,32);error.source_sha256=coverage.digest(document)
                rejection.write_rejection(source_path,source_path.with_name('receipt.json'),scope,nonce,error)
                rejected.append(rejection.validate_rejection(source_path,scope,nonce,started))
            else:runner.immutable_json(source_path.with_name('receipt.json'),{'stage':'verified'})
        runner.immutable_json(output,{'rejected_days':rejected,'started_at':started})
    monkeypatch.setattr(worker,'read_process',process)
    worker.main();value=json.loads(capsys.readouterr().out)
    assert value['stage']=='trip_worker_partial' and value['acceptance']=='PARTIAL'
    assert value['rejected_days']==['2026-10-19'] and value['coverage']['complete_through'] is None
