#!/usr/bin/env python3
"""One prepared debt's evidence only; default read-only plan, never import money."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID
import psycopg2
import psycopg2.extras
try:
    from .source_evidence import normalize_source_evidence, append_source_evidence, latest_source_evidence, _digest, _instant
except ImportError:
    from source_evidence import normalize_source_evidence, append_source_evidence, latest_source_evidence, _digest, _instant


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_capture(document, tenant_id, handoff, now):
    if (document.get('schema_version') != 1 or document.get('capture_kind') != 'ets_target_invoice_evidence'
            or document.get('tenant_id') != str(tenant_id)):
        raise ValueError('Capture tenant or format mismatch')
    evidence = normalize_source_evidence(document.get('sourceEvidence'))
    if evidence is None:
        raise ValueError('Invalid normalized source evidence')
    keys = {'ets_shop_id':'ets_shop_id','service_id':'source_service_number',
            'service_internal_id':'ets_service_internal_id','invoice_service_id':'ets_service_internal_id',
            'invoice_id':'ets_invoice_internal_id','invoice_number':'source_invoice_number'}
    if any(evidence.get(k) != str(handoff[v]) for k,v in keys.items()):
        raise ValueError('Capture source identity mismatch')
    authorization = handoff.get('bill_to_authorization') or {}
    if (authorization.get('mode') != 'same_customer' and handoff.get('source_customer_id')
            and str(handoff.get('source_customer_id')) != str(handoff.get('customer_id'))
            and evidence.get('source_customer_binding_kind') != 'embedded_service_customer'):
        raise ValueError('Cross-customer handoff requires captured source customer proof')
    # Preserve source-customer drift as a digest-bound revision; activation and
    # receipt reconciliation compare it with immutable legal-bill-to authority.
    manifest = evidence.get('invoice_manifest') or {}
    if (manifest.get('complete') is not True or manifest.get('invoice_ids') != [str(handoff['ets_invoice_internal_id'])]
            or manifest.get('service_internal_id') != str(handoff['ets_service_internal_id'])):
        raise ValueError('Complete singleton source manifest required')
    stamp = _instant(evidence.get('observed_at_source'))
    ack = handoff['owner_acknowledged_at']
    if not stamp or stamp <= ack or stamp > now or now-stamp > timedelta(hours=24):
        raise ValueError('Source confirmation must be fresh and after owner acknowledgement')
    return evidence


def fingerprint(cur, tenant_id, invoice_ids):
    # Raw server JSON text keeps exact cents. Do not include the one metadata
    # column this operation is explicitly authorized to change.
    scopes = {
        'invoices':("id = ANY(%s)", ' - \'ets_source_evidence\''),
        'payments':("invoice_id = ANY(%s)", ''),
        'invoice_settlements':("invoice_id = ANY(%s)", ''),
        'invoice_payment_attempts':("invoice_id = ANY(%s)", ''),
        'invoice_payment_ledger_events':("invoice_id = ANY(%s)", ''),
        'payment_refunds':("invoice_id = ANY(%s)", ''),
        'payment_overpayments':("invoice_id = ANY(%s)", ''),
        'customer_credit_entries':("target_invoice_id = ANY(%s)", ''),
        'payment_accounting_links':("invoice_id = ANY(%s)", ''),
        'provider_outbox':("aggregate_id = ANY(%s)", ''),
        'ets_receipt_update_tasks':("invoice_id = ANY(%s)", ''),
        'source_receipt_links':("handoff_id IN (SELECT id FROM source_debt_handoffs h WHERE h.tenant_id=t.tenant_id AND h.source_dbn_invoice_id=ANY(%s))", ''),
        'source_debt_events':("handoff_id IN (SELECT id FROM source_debt_handoffs h WHERE h.tenant_id=t.tenant_id AND h.source_dbn_invoice_id=ANY(%s))", ''),
        'source_debt_handoffs':("source_dbn_invoice_id = ANY(%s)", ''),
    }
    result = {}
    for table,(scope,exclude) in scopes.items():
        cur.execute(f"SELECT COALESCE(jsonb_agg(to_jsonb(t){exclude} ORDER BY id)::text,'[]') AS snapshot FROM {table} t WHERE tenant_id=%s AND {scope}", (tenant_id, invoice_ids))
        result[table] = hashlib.sha256(cur.fetchone()['snapshot'].encode()).hexdigest()
    return result


def persist(conn, args, document):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        key=int.from_bytes(hashlib.sha256(f'dieselbridge:financial:v1:{args.tenant_id}'.encode()).digest()[:8], 'big', signed=True)
        if args.commit:
            cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(key,))
            if not cur.fetchone()['acquired']:
                raise ValueError('Tenant financial processing is busy')
        cur.execute('SELECT * FROM source_debt_handoffs WHERE tenant_id=%s AND id=%s'+(' FOR UPDATE' if args.commit else ''),(args.tenant_id,args.handoff_id))
        handoff=cur.fetchone()
        if not handoff or str(handoff['source_dbn_invoice_id']) != str(args.invoice_id):
            raise ValueError('Prepared source debt identity unavailable')
        if args.expected_version is not None and handoff['version'] != args.expected_version:
            raise ValueError('Handoff version changed')
        cur.execute("SELECT id, repair_order_id, invoice_number, source, deleted_at, ets_source_evidence FROM invoices WHERE tenant_id=%s AND id=%s"+(' FOR UPDATE' if args.commit else ''),(args.tenant_id,args.invoice_id))
        invoice=cur.fetchone()
        if (not invoice or invoice['source']!='easy_truck_shop_import' or invoice['deleted_at'] is not None
                or invoice['repair_order_id'] != handoff['source_repair_order_id']
                or invoice['invoice_number'] != 'ETSINV-'+str(handoff['source_invoice_number'])):
            raise ValueError('Source invoice ownership mismatch')
        envelope=invoice['ets_source_evidence']
        prior=digest(envelope)
        if args.expected_envelope_sha256 is not None and prior != args.expected_envelope_sha256:
            raise ValueError('Source envelope changed')
        evidence=validate_capture(document,args.tenant_id,handoff,datetime.now(timezone.utc))
        updated=append_source_evidence(envelope,evidence)
        if updated == envelope or updated.get('revision_capacity_exceeded') or latest_source_evidence(updated) != evidence:
            raise ValueError('New source confirmation was not retained')
        row=updated['observations'][-1]
        confirmation=updated.get('latest_confirmation')
        if row['sha256'] != _digest(row['evidence']) or (confirmation and confirmation['sha256'] != row['sha256']):
            raise ValueError('Source digest verification failed')
        report={'mode':'commit' if args.commit else 'dry-run','handoff_version':handoff['version'],
                'prior_envelope_sha256':prior,'next_envelope_sha256':digest(updated),'source_invoice_number':handoff['source_invoice_number'],
                'source_observed_at':evidence['observed_at_source'],'financial_state_unchanged':True}
        if args.commit:
            ids=[args.invoice_id]+([handoff['native_invoice_id']] if handoff.get('native_invoice_id') else [])
            before=fingerprint(cur,args.tenant_id,ids)
            cur.execute('UPDATE invoices SET ets_source_evidence=%s WHERE tenant_id=%s AND id=%s', (psycopg2.extras.Json(updated),args.tenant_id,args.invoice_id))
            if cur.rowcount != 1 or fingerprint(cur,args.tenant_id,ids) != before:
                raise ValueError('Financial state changed; evidence update rolled back')
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['tenant-id','handoff-id','invoice-id']: parser.add_argument('--'+name,type=UUID,required=True)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--expected-capture-sha256')
    parser.add_argument('--expected-envelope-sha256')
    parser.add_argument('--expected-version',type=int)
    parser.add_argument('--commit',action='store_true')
    a=parser.parse_args()
    if a.commit and (not a.expected_capture_sha256 or not a.expected_envelope_sha256 or not a.expected_version):
        parser.error('Commit requires exact capture/envelope digests and handoff version')
    raw=a.capture.read_bytes()
    if len(raw)>262144 or a.capture.stat().st_mode & 0o077:
        parser.error('Bounded owner-only capture file required')
    capture_sha=hashlib.sha256(raw).hexdigest()
    if a.expected_capture_sha256 and a.expected_capture_sha256 != capture_sha:
        parser.error('Capture digest changed')
    document=json.loads(raw)
    url=os.environ.get('DATABASE_URL')
    if not url: parser.error('Approved DATABASE_URL required; no fallback database')
    url=url.replace('postgresql+asyncpg://','postgresql://',1)
    psycopg2.extras.register_uuid()
    with psycopg2.connect(url) as conn:
        conn.set_session(isolation_level='SERIALIZABLE',readonly=not a.commit)
        report=persist(conn,a,document)
        report['capture_sha256']=capture_sha
        if a.commit: conn.commit()
        else: conn.rollback()
    print(json.dumps(report,sort_keys=True))

if __name__=='__main__':
    try:main()
    except ValueError as exc:raise SystemExit(str(exc))
    except Exception as exc:raise SystemExit('Evidence operation held; transaction rolled back ('+type(exc).__name__+')')
