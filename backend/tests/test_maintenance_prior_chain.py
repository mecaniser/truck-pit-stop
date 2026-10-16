from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceCompletion as Completion
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.schemas import maintenance as wire
from app.services import maintenance as service
from test_service_checklists import seed
from test_maintenance_programs import create

@pytest.fixture
def db_session(db_session):
    db_session.autoflush=False
    return db_session

def actual(days,miles):
    return {'performed_on':(datetime.now(timezone.utc).date()-timedelta(days=days)).isoformat(),'confirm_actual_service_readings':True,'readings':{'odometer_miles':{'kind':'manual','value':str(miles),'basis':'staff_observed','note':None},'engine_hours':None}}

async def evidence(db,a,p,intent):
    await db.refresh(p)
    raw={'purpose':'evidence','channel':'shop','program':{'program_id':str(p.id),'expected_version':p.version},'evidence':intent}
    preview=await service.target_preview(db,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
    body=wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'})
    return await service.evidence_command(db,a.owner,a.vehicle.id,body,str(uuid4()))

async def source(db,a,name):
    row=RepairOrder(id=uuid4(),tenant_id=a.tenant.id,customer_id=a.customer.id,vehicle_id=a.vehicle.id,order_number=name,status=RepairOrderStatus.COMPLETED,description=name,work_completed_at=datetime.now(timezone.utc))
    db.add(row);await db.commit();return row

@pytest.mark.asyncio
@pytest.mark.parametrize('depth',[1,3])
async def test_revoke_later_completion_restores_prior_reaffirmed_targets(db_session,depth):
    a=await seed(db_session);a.order.status=RepairOrderStatus.COMPLETED;await db_session.commit()
    saved,_=await create(db_session,a);p=await db_session.get(Program,UUID(saved['program']['id']))
    first=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(a.order.id)},'attestation':actual(10,100000)})
    reaffirmed=first
    for _ in range(depth):
        reaffirmed=await evidence(db_session,a,p,{'action':'reaffirm','completion_id':reaffirmed['completion']['id'],'reason':'Rechecked original source','acknowledged_work_link_ids':[]})
    second_source=await source(db_session,a,'INDEPENDENT-SECOND')
    second=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(second_source.id)},'attestation':actual(5,110000)})
    assert second['program']['targets']['odometer_miles']==111000
    revoked=await evidence(db_session,a,p,{'action':'revoke','completion_id':second['completion']['id'],'reason':'Second service was entered incorrectly','acknowledged_work_link_ids':[]})
    assert revoked['program']['targets']==reaffirmed['program']['targets'],(revoked['program']['targets'],reaffirmed['program']['targets'])
    assert p.controlling_completion_id==UUID(reaffirmed['completion']['id'])

@pytest.mark.asyncio
async def test_correcting_older_source_does_not_clear_newer_controller_review(db_session):
    a=await seed(db_session);a.order.status=RepairOrderStatus.COMPLETED;await db_session.commit()
    saved,_=await create(db_session,a);p=await db_session.get(Program,UUID(saved['program']['id']))
    first=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(a.order.id)},'attestation':actual(10,100000)})
    second_source=await source(db_session,a,'INDEPENDENT-CURRENT')
    second=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(second_source.id)},'attestation':actual(5,110000)})
    await service.order_lifecycle(db_session,a.owner,second_source,'source_update')
    second_source.mileage_out=110001;await db_session.commit();await db_session.refresh(p)
    assert p.review_codes==['source_changed']
    corrected=await evidence(db_session,a,p,{'action':'reaffirm','completion_id':first['completion']['id'],'reason':'Verify older original service','acknowledged_work_link_ids':[]})
    assert p.controlling_completion_id==UUID(second['completion']['id'])
    assert corrected['program']['review']['required'] and 'source_changed' in corrected['program']['review']['codes'],corrected['program']['review']

@pytest.mark.asyncio
async def test_old_resolved_pending_source_change_does_not_dispute_newer_controller(db_session):
    from test_maintenance_evidence import work,reviewed
    from app.db.models.maintenance import MaintenanceWorkLink as Link
    a,_,order,_=await work(db_session)
    review,_=await reviewed(db_session,a,order,[None,None])
    prepared=await service.prepare_finalization(db_session,a.owner,order,review,channel='shop')
    order.status=RepairOrderStatus.COMPLETED;await service.finish_finalization(db_session,a.owner,order,prepared);await db_session.commit()
    link=await db_session.scalar(select(Link).where(Link.repair_order_id==order.id).order_by(Link.id))
    p=await db_session.get(Program,link.program_id)
    await evidence(db_session,a,p,{'action':'resolve_pending','work_link_id':str(link.id),'expected_link_version':link.version,'attestation':actual(10,100000)})
    newer_source=await source(db_session,a,'INDEPENDENT-NEWER')
    newer=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(newer_source.id)},'attestation':actual(5,110000)})
    await service.order_lifecycle(db_session,a.owner,order,'source_update');order.mileage_out=100001;await db_session.commit()
    view=await service.program_view(db_session,a.owner,'shop',p,a.vehicle,a.tenant,datetime.now(timezone.utc))
    assert p.controlling_completion_id==UUID(newer['completion']['id'])
    assert not view['review']['required'],view['review']


@pytest.mark.asyncio
async def test_reaffirmed_history_only_chain_is_never_selected_as_prior_controller(db_session):
    a=await seed(db_session);a.order.status=RepairOrderStatus.COMPLETED;await db_session.commit()
    saved,_=await create(db_session,a);p=await db_session.get(Program,UUID(saved['program']['id']))
    first=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(a.order.id)},'attestation':actual(8,100000)})
    older_source=await source(db_session,a,'OLDER-HISTORY')
    older=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(older_source.id)},'attestation':actual(10,90000)})
    assert older['completion']['result']=='history_only'
    await evidence(db_session,a,p,{'action':'reaffirm','completion_id':older['completion']['id'],'reason':'Verified older history only','acknowledged_work_link_ids':[]})
    next_source=await source(db_session,a,'LATER-CONTROLLER')
    later=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(next_source.id)},'attestation':actual(5,110000)})
    revoked=await evidence(db_session,a,p,{'action':'revoke','completion_id':later['completion']['id'],'reason':'Erroneous later entry','acknowledged_work_link_ids':[]})
    assert revoked['program']['targets']==first['program']['targets']
    assert p.controlling_completion_id==UUID(first['completion']['id'])


@pytest.mark.asyncio
async def test_revoked_reaffirmed_chain_cannot_return_as_prior_controller(db_session):
    a=await seed(db_session);a.order.status=RepairOrderStatus.COMPLETED;await db_session.commit()
    baseline,_=await create(db_session,a);p=await db_session.get(Program,UUID(baseline['program']['id']))
    first=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(a.order.id)},'attestation':actual(10,100000)})
    accepted=await evidence(db_session,a,p,{'action':'reaffirm','completion_id':first['completion']['id'],'reason':'Checked earlier entry','acknowledged_work_link_ids':[]})
    await evidence(db_session,a,p,{'action':'revoke','completion_id':accepted['completion']['id'],'reason':'Earlier entry was incorrect','acknowledged_work_link_ids':[]})
    next_source=await source(db_session,a,'LATER-AFTER-REVOKED')
    later=await evidence(db_session,a,p,{'action':'recognize','source':{'kind':'repair_order','id':str(next_source.id)},'attestation':actual(5,110000)})
    revoked=await evidence(db_session,a,p,{'action':'revoke','completion_id':later['completion']['id'],'reason':'Later entry was incorrect','acknowledged_work_link_ids':[]})
    assert revoked['program']['targets']==baseline['program']['targets'] and p.controlling_completion_id is None
