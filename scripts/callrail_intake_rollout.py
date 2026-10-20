"""Review/apply an explicit CallRail number manifest without changing forwarding.

Run inside the deployed application environment. Default mode is read-only.
Provider requests are GET-only. No customer, message or conversation is modified.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from app.core.config import settings
from app.db.models.callrail import CallRailNumberBinding
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def provider_inventory(manifest):
    account = manifest['account_id']
    require(re.fullmatch(r'[A-Za-z0-9]+', account), 'Invalid provider account')
    credential = os.environ.get(manifest['credential_ref'])
    require(bool(credential), 'Configured provider credential unavailable')
    def get(path):
        request = urllib.request.Request('https://api.callrail.com/v3/a/' + account + '/' + path,
            headers={'Authorization': 'Token token=' + credential}, method='GET')
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    data = get('trackers.json?company_id=' + manifest['company_id'] + '&per_page=250')
    require(data.get('total_pages') == 1, 'Inventory pagination changed; review required')
    actual, snapshots = {}, []
    for row in data.get('trackers', []):
        if row.get('status') != 'active' or not row.get('sms_enabled') or not row.get('sms_supported'):
            continue
        record = get('trackers/' + row['id'] + '.json')
        require(record.get('company', {}).get('id') == manifest['company_id'], 'Foreign company tracker')
        require(record.get('status') == 'active' and record.get('sms_enabled') is True
                and record.get('sms_supported') is True, 'Tracker availability changed')
        keys = ('id', 'company', 'tracking_numbers', 'destination_number', 'call_flow', 'message_flow',
                'sms_enabled', 'sms_supported', 'status', 'source', 'name', 'sip_trunk', 'whisper_message')
        require(all(key in record for key in keys), 'Incomplete forwarding baseline')
        snapshots.append({key: record[key] for key in keys})
        for phone in record['tracking_numbers']:
            require(phone not in actual, 'Duplicate provider number')
            actual[phone] = record['id']
    expected = {row['sender_phone']: row['tracker_id'] for row in manifest['numbers']}
    require(len(expected) == len(manifest['numbers']) and actual == expected,
            'Number inventory changed; review manifest before activation')
    return digest(sorted(snapshots, key=lambda row: row['id']))


async def run(args):
    require(not (args.apply and args.hold), 'Choose activation or intake hold')
    manifest = json.loads(args.manifest_json) if args.manifest_json else json.loads(Path(args.manifest).read_text())
    tenant_id = UUID(manifest['tenant_id'])
    for key in ('credential_ref', 'signing_secret_ref'):
        require(re.fullmatch(r'CALLRAIL_[A-Z0-9_]+', manifest[key]), 'Invalid dedicated credential reference')
        if not args.hold:
            require(bool(os.environ.get(manifest[key])), 'Required dedicated credential unavailable')
    require(re.fullmatch(r'[A-Za-z0-9]+', manifest['company_id']), 'Invalid company identifier')
    require(all(re.fullmatch(r'\+1[2-9][0-9]{9}', row['sender_phone'])
                and row.get('accept_new_inquiries') is True for row in manifest['numbers']), 'Invalid number manifest')
    require(all(not getattr(settings, name) for name in (
        'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED')),
        'New routing/automation/recovery flags must remain off')
    mutation = args.apply or args.hold
    if mutation:
        require(os.environ.get('RAILWAY_GIT_COMMIT_SHA') == args.expected_sha
                and re.fullmatch(r'[0-9a-f]{40}', args.expected_sha or ''), 'Deployed source mismatch')
    inventory_hash = None if args.hold else await asyncio.to_thread(provider_inventory, manifest)
    if args.apply:
        require(args.expected_inventory_hash == inventory_hash, 'Provider baseline changed since review')
    plans = []
    async with AsyncSessionLocal() as db:
        versions = list((await db.execute(text('SELECT version_num FROM alembic_version'))).scalars())
        require(versions == [args.expected_schema], 'Schema mismatch')
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
        require(tenant and tenant.deleted_at is None and tenant.is_active and tenant.messaging_enabled,
                'Shop inactive or messaging disabled')
        # Match staff sender selection's UUID lock order to avoid a rollback deadlock.
        await db.execute(select(CallRailNumberBinding).where(
            CallRailNumberBinding.account_id == manifest['account_id'],
            CallRailNumberBinding.sender_phone.in_([row['sender_phone'] for row in manifest['numbers']])
        ).order_by(CallRailNumberBinding.id).with_for_update())
        for row in manifest['numbers']:
            binding = await db.scalar(select(CallRailNumberBinding).where(
                CallRailNumberBinding.account_id == manifest['account_id'],
                CallRailNumberBinding.sender_phone == row['sender_phone']).with_for_update())
            expected = dict(tenant_id=tenant_id, account_id=manifest['account_id'],
                company_id=manifest['company_id'], tracker_id=row['tracker_id'], sender_phone=row['sender_phone'],
                credential_ref=manifest['credential_ref'], signing_secret_ref=manifest['signing_secret_ref'])
            if binding:
                require(binding.deleted_at is None and (args.hold or binding.enabled)
                        and all(getattr(binding, key) == value for key, value in expected.items()),
                        'Existing number ownership/configuration changed')
            elif args.hold:
                continue
            before = bool(binding.accept_new_inquiries) if binding else False
            identifier = binding.id if binding else uuid5(NAMESPACE_URL,
                'dieselbridge:callrail:' + str(tenant_id) + ':' + manifest['account_id'] + ':' + row['sender_phone'])
            plans.append(dict(binding_id=str(identifier), sender_phone=row['sender_phone'],
                existing=binding is not None, intake_before=before, intake_after=not args.hold))
            if args.apply and binding is None:
                binding = CallRailNumberBinding(id=identifier, **expected, enabled=True, accept_new_inquiries=True)
                db.add(binding)
            elif mutation:
                binding.accept_new_inquiries = not args.hold
        if mutation:
            await db.commit()
        else:
            await db.rollback()
    print('INTAKE_ROLLOUT=' + json.dumps(dict(mode='hold' if args.hold else 'apply' if args.apply else 'review',
        inventory_hash=inventory_hash, numbers=plans, forwarding_changed=False, conversations_changed=False,
        automation=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--manifest')
    source.add_argument('--manifest-json')
    parser.add_argument('--expected-schema', required=True)
    parser.add_argument('--expected-sha')
    parser.add_argument('--expected-inventory-hash')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--hold', action='store_true')
    asyncio.run(run(parser.parse_args()))
