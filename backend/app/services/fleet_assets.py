"""Canonical equipment classification and tenant-safe physical attachments.

Pairing changes only an attachment timeline. Repair orders, maintenance, account
relationships and telemetry continue to belong to each original Vehicle id.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.db.models.customer import Customer
from app.db.models.fleet_asset_attachment import FleetAssetAttachment
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet import FleetAttachedAsset


def _fail(status, message):
    raise HTTPException(status, message)


async def lock_tenant(db, tenant_id):
    # A single ordering point covers attach, swaps, detach and classification.
    # PostgreSQL row locks plus the active unique indexes prevent two requests
    # from both observing an available trailer and creating competing pairings.
    tenant = (await db.execute(select(Tenant.id).where(
        Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True),
    ).with_for_update())).scalar_one_or_none()
    if tenant is None:
        _fail(404, "Fleet asset not found")


async def _visible_assets(db, tenant_id, ids, *, lock=False, require_membership=True):
    if not ids:
        return {}
    stamp = datetime.now(timezone.utc)
    # EXISTS avoids duplicate memberships and nullable-join FOR UPDATE errors.
    membership = select(FleetMembership.id).where(
        FleetMembership.vehicle_id == Vehicle.id,
        FleetMembership.tenant_id == tenant_id,
        FleetMembership.deleted_at.is_(None),
        FleetMembership.effective_from <= stamp,
        FleetMembership.effective_to.is_(None),
    ).exists()
    query = select(Vehicle).join(Customer, Customer.id == Vehicle.customer_id).where(
        Vehicle.tenant_id == tenant_id, Vehicle.id.in_(ids),
        Vehicle.deleted_at.is_(None), Customer.tenant_id == tenant_id,
        Customer.deleted_at.is_(None),
    ).order_by(Vehicle.id).execution_options(populate_existing=True)
    if require_membership:
        query = query.where(membership)
    if lock:
        query = query.with_for_update(of=Vehicle)
    return {asset.id: asset for asset in (await db.execute(query)).scalars().all()}


def _active():
    return FleetAssetAttachment.detached_at.is_(None), FleetAssetAttachment.deleted_at.is_(None)


def _other(pair, asset_id):
    return pair.trailer_id if pair.tractor_id == asset_id else pair.tractor_id


async def attach(db, cards, tenant_id):
    """Fresh bounded enrichment covers both cached board rows and detail cards."""
    ids = [card.id for card in cards]
    if not ids:
        return
    pairs = (await db.execute(select(FleetAssetAttachment).where(
        FleetAssetAttachment.tenant_id == tenant_id, *_active(),
        or_(FleetAssetAttachment.tractor_id.in_(ids), FleetAssetAttachment.trailer_id.in_(ids)),
    ))).scalars().all()
    all_ids = set(ids)
    for pair in pairs:
        all_ids.update((pair.tractor_id, pair.trailer_id))
    assets = await _visible_assets(db, tenant_id, all_ids)
    # Existing board compatibility paths can display a future membership.
    # Its canonical classification is still known even though it cannot yet
    # participate in an attachment. Never replace that known type with unknown.
    canonical_assets = await _visible_assets(db, tenant_id, ids, require_membership=False)
    pair_by_asset = {}
    for pair in pairs:
        tractor, trailer = assets.get(pair.tractor_id), assets.get(pair.trailer_id)
        # Fail closed if an asset has left the board, been archived, or an
        # out-of-band classification change invalidated the original roles.
        if tractor and trailer and tractor.equipment_type == "tractor" and trailer.equipment_type == "trailer":
            pair_by_asset[tractor.id] = pair
            pair_by_asset[trailer.id] = pair
    for card in cards:
        asset = canonical_assets.get(card.id)
        card.equipment_type = asset.equipment_type if asset else "unknown"
        card.attached_asset = None
        pair = pair_by_asset.get(card.id)
        if pair:
            counterpart = assets[_other(pair, card.id)]
            card.attached_asset = FleetAttachedAsset(
                id=counterpart.id, unit_number=counterpart.unit_number,
                equipment_type=counterpart.equipment_type, attached_at=pair.attached_at,
            )


async def change_attachment(db, actor, asset_id: UUID, attached_vehicle_id: UUID | None,
                            expected_attached_vehicle_id: UUID | None):
    await lock_tenant(db, actor.tenant_id)
    assets = await _visible_assets(db, actor.tenant_id, [asset_id], lock=True)
    if asset_id not in assets:
        _fail(404, "Fleet asset not found")
    equipment_type = assets[asset_id].equipment_type
    await save_settings(db, actor, asset_id, equipment_type, attached_vehicle_id,
                        equipment_type, expected_attached_vehicle_id)


async def _current_pair(db, tenant_id, asset_id):
    return (await db.execute(select(FleetAssetAttachment).where(
        FleetAssetAttachment.tenant_id == tenant_id, *_active(),
        or_(FleetAssetAttachment.tractor_id == asset_id, FleetAssetAttachment.trailer_id == asset_id),
    ).with_for_update())).scalar_one_or_none()


async def _close_pair(db, pair, actor_id, stamp):
    if pair:
        pair.detached_at = stamp
        pair.detached_by_user_id = actor_id
        await db.flush()


async def _create_pair(db, actor, tractor_id, trailer_id, stamp):
    db.add(FleetAssetAttachment(
        tenant_id=actor.tenant_id, tractor_id=tractor_id, trailer_id=trailer_id,
        attached_at=stamp, attached_by_user_id=actor.id,
    ))
    await db.flush()


async def save_settings(db, actor, asset_id, equipment_type, attached_vehicle_id,
                        expected_equipment_type, expected_attached_vehicle_id):
    """One atomic details save; an active trailer always ends with a tractor."""
    await lock_tenant(db, actor.tenant_id)
    ids = {asset_id}
    if attached_vehicle_id:
        ids.add(attached_vehicle_id)
    assets = await _visible_assets(db, actor.tenant_id, ids, lock=True)
    if len(assets) != len(ids):
        _fail(404, "Fleet asset not found")
    asset = assets[asset_id]
    if attached_vehicle_id == asset_id:
        _fail(409, "An asset cannot attach to itself")
    current = await _current_pair(db, actor.tenant_id, asset_id)
    current_id = _other(current, asset_id) if current else None
    # A repeated successful request is harmless. A stale request with a
    # different intended result cannot silently detach or swap a newer link.
    if asset.equipment_type == equipment_type and current_id == attached_vehicle_id:
        if equipment_type == "trailer" and not current:
            _fail(409, "A fleet trailer requires a tractor")
        return
    if current_id != expected_attached_vehicle_id or asset.equipment_type != expected_equipment_type:
        _fail(409, "Equipment settings changed; refresh the asset before trying again")
    if current and current.tractor_id == asset_id:
        # Replacing a tractor's current trailer would strand that trailer on
        # the fleet. Move the trailer to a free tractor or remove it first.
        _fail(409, "Reassign or remove the current trailer before changing this tractor's attachment or type")
    if equipment_type == "trailer" and attached_vehicle_id is None:
        _fail(409, "A fleet trailer requires a tractor")
    counterpart = assets.get(attached_vehicle_id)
    if counterpart:
        if {equipment_type, counterpart.equipment_type} != {"tractor", "trailer"}:
            _fail(409, "Attach a classified tractor to a classified trailer")
        occupied = await _current_pair(db, actor.tenant_id, counterpart.id)
        if occupied and (not current or occupied.id != current.id):
            _fail(409, "The selected asset is already attached; choose a free tractor")
    stamp = datetime.now(timezone.utc)
    await _close_pair(db, current, actor.id, stamp)
    asset.equipment_type = equipment_type
    if counterpart:
        tractor, trailer = (asset, counterpart) if equipment_type == "tractor" else (counterpart, asset)
        await _create_pair(db, actor, tractor.id, trailer.id, stamp)
    await db.flush()


async def has_valid_tractor(db, tenant_id, trailer_id):
    pair = await _current_pair(db, tenant_id, trailer_id)
    if not pair or pair.trailer_id != trailer_id:
        return False
    tractors = await _visible_assets(db, tenant_id, [pair.tractor_id])
    return bool(tractors and tractors[pair.tractor_id].equipment_type == "tractor")


async def guard_membership_entry(db, tenant_id, asset_id):
    """Shared admission point for every canonical membership writer."""
    await lock_tenant(db, tenant_id)
    assets = await _visible_assets(db, tenant_id, [asset_id], lock=True, require_membership=False)
    if asset_id not in assets:
        _fail(404, "Fleet asset not found")
    if assets[asset_id].equipment_type == "trailer" and not await has_valid_tractor(db, tenant_id, asset_id):
        _fail(409, "Select a tractor when adding a trailer to the fleet")


async def enroll_trailer(db, actor, trailer_id, fleet_customer_id, tractor_id):
    """Pair and enroll an off-fleet trailer in one transaction."""
    from app.services.vehicle_identity import ensure_fleet_membership
    await lock_tenant(db, actor.tenant_id)
    assets = await _visible_assets(db, actor.tenant_id, [trailer_id], lock=True, require_membership=False)
    tractors = await _visible_assets(db, actor.tenant_id, [tractor_id], lock=True) if tractor_id else {}
    if trailer_id not in assets or tractor_id not in tractors:
        _fail(404, "Fleet asset not found")
    if assets[trailer_id].equipment_type != "trailer" or tractors[tractor_id].equipment_type != "tractor":
        _fail(409, "A fleet trailer requires a classified tractor")
    current = await _current_pair(db, actor.tenant_id, trailer_id)
    occupied = await _current_pair(db, actor.tenant_id, tractor_id)
    if current and current.tractor_id != tractor_id:
        _fail(409, "This trailer is already attached; reassign it from equipment settings")
    if occupied and occupied.trailer_id != trailer_id:
        _fail(409, "The selected tractor already has a trailer")
    if not current:
        await _create_pair(db, actor, tractor_id, trailer_id, datetime.now(timezone.utc))
    return await ensure_fleet_membership(db, tenant_id=actor.tenant_id, vehicle_id=trailer_id,
                                       fleet_customer_id=fleet_customer_id)


async def prepare_membership_exit(db, tenant_id, membership, actor_id=None):
    """The last trailer membership closes its pair; tractors cannot strand it."""
    await lock_tenant(db, tenant_id)
    stamp = datetime.now(timezone.utc)
    remaining = (await db.execute(select(FleetMembership).where(
        FleetMembership.tenant_id == tenant_id, FleetMembership.vehicle_id == membership.vehicle_id,
        FleetMembership.id != membership.id, FleetMembership.effective_to.is_(None),
        FleetMembership.deleted_at.is_(None),
    ))).scalars().all()
    if any((row.effective_from.replace(tzinfo=timezone.utc) if row.effective_from.tzinfo is None else row.effective_from) <= stamp for row in remaining):
        return
    pair = await _current_pair(db, tenant_id, membership.vehicle_id)
    if not pair:
        return
    if pair.tractor_id == membership.vehicle_id:
        _fail(409, "Reassign or remove this tractor's trailer before removing the tractor from the fleet")
    if remaining:
        _fail(409, "Resolve scheduled fleet memberships before removing this trailer")
    await _close_pair(db, pair, actor_id, stamp)


async def change_equipment_type(db, vehicle, equipment_type):
    """Used by every classification edit, including company equipment."""
    await lock_tenant(db, vehicle.tenant_id)
    # Discard a pre-lock classification snapshot if another writer committed.
    await db.refresh(vehicle, attribute_names=["equipment_type"])
    if vehicle.equipment_type == equipment_type:
        return
    pair = (await db.execute(select(FleetAssetAttachment.id).where(
        FleetAssetAttachment.tenant_id == vehicle.tenant_id, *_active(),
        or_(FleetAssetAttachment.tractor_id == vehicle.id, FleetAssetAttachment.trailer_id == vehicle.id),
    ))).scalar_one_or_none()
    if pair:
        _fail(409, "Use equipment settings to change attached equipment")
    if equipment_type == "trailer":
        membership = (await db.execute(select(FleetMembership.id).where(
            FleetMembership.tenant_id == vehicle.tenant_id, FleetMembership.vehicle_id == vehicle.id,
            FleetMembership.effective_to.is_(None), FleetMembership.deleted_at.is_(None),
        ).limit(1))).scalar_one_or_none()
        if membership:
            _fail(409, "Select a tractor in equipment settings when classifying a fleet trailer")
    vehicle.equipment_type = equipment_type


async def guard_lifecycle_change(db, tenant_id, vehicle_ids):
    """Prevent hidden live pairings when an asset is removed, merged or archived.

    Call before any vehicle row locks; attachment writes lock tenant then asset.
    Closed historical pairings remain associated with their original identities.
    """
    await lock_tenant(db, tenant_id)
    if not vehicle_ids:
        return
    active = (await db.execute(select(FleetAssetAttachment.id).where(
        FleetAssetAttachment.tenant_id == tenant_id, *_active(),
        or_(FleetAssetAttachment.tractor_id.in_(vehicle_ids),
            FleetAssetAttachment.trailer_id.in_(vehicle_ids)),
    ).limit(1))).scalar_one_or_none()
    if active:
        _fail(409, "Remove attached trailers from the fleet before archiving, merging or changing these equipment relationships")
