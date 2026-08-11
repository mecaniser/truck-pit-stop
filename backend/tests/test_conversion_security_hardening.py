import json
import os
import socket
import ssl
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import admin, conversion_exports
from app.core.paid_invoice_webhook_crypto import (
    decrypt_paid_invoice_webhook_secret,
    encrypt_paid_invoice_webhook_secret,
    reencrypt_paid_invoice_webhook_secret,
)
from app.core.webhook_destination import resolve_webhook_destination
from app.db.models.conversion_export_audit import ConversionExportAudit
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.conversion_pii_retention_service import (
    erase_customer_conversion_event_pii,
    purge_expired_conversion_event_pii,
)
from app.services.paid_invoice_webhook_key_rotation import rotate_paid_invoice_webhook_secrets
from app.services.paid_invoice_webhook_service import (
    _deliver,
    conversion_signature,
    enqueue_paid_invoice_webhook,
    process_due_paid_invoice_webhooks,
    verify_conversion_signature,
)
from app.services.provider_outbox_service import ProviderDeliveryError


def _dns(addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.mark.asyncio
async def test_destination_resolution_preserves_authority_and_deduplicates(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _dns(["93.184.216.34", "93.184.216.34"]))
    destination = await resolve_webhook_destination("https://hooks.example.com:8443/a/path?q=1")
    assert destination.addresses == ("93.184.216.34",)
    assert destination.tls_hostname == "hooks.example.com"
    assert destination.host_header == "hooks.example.com:8443"


@pytest.mark.asyncio
async def test_mixed_public_private_dns_answer_is_rejected(monkeypatch):
    from app.core.webhook_destination import WebhookDestinationError
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _dns(["93.184.216.34", "169.254.169.254"]))
    with pytest.raises(WebhookDestinationError, match="public"):
        await resolve_webhook_destination("https://hooks.example.com/path")


@pytest.mark.asyncio
async def test_delivery_uses_one_dns_snapshot_and_pinned_ip(monkeypatch):
    calls = 0

    def first_dns(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            return _dns(["127.0.0.1"])
        return _dns(["93.184.216.34"])

    monkeypatch.setattr(socket, "getaddrinfo", first_dns)
    destination = await resolve_webhook_destination("https://hooks.example.com/a/path?q=1")

    async def fixed_destination(_url):
        return destination

    captured = {}

    class Response:
        status_code = 202
        headers = {}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return Response()

    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", fixed_destination)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant = Tenant(name="Pinned", slug=f"pinned-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url=destination.original_url, paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("secret-value"))
    event = ProviderOutboxEvent(tenant_id=uuid4(), event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(), payload={}, idempotency_key="pinned-delivery")
    await _deliver(tenant, event)
    assert calls == 1
    assert captured["url"].host == "93.184.216.34"
    assert captured["url"].path == "/a/path"
    assert captured["url"].query == b"q=1"
    assert captured["headers"]["Host"] == "hooks.example.com"
    assert captured["extensions"]["sni_hostname"] == "hooks.example.com"


@pytest.mark.asyncio
async def test_only_connect_failure_tries_next_vetted_ip(monkeypatch):
    from app.core.webhook_destination import ResolvedWebhookDestination
    destination = ResolvedWebhookDestination("https://hooks.example.com/path", "hooks.example.com", "hooks.example.com", ("93.184.216.34", "93.184.216.35"))

    async def fixed(_url): return destination
    attempts = []

    class Response:
        status_code = 204
        headers = {}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, _method, url, **_kwargs):
            attempts.append(url.host)
            if len(attempts) == 1:
                raise httpx.ConnectError("connect failed", request=httpx.Request("POST", url))
            return Response()

    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", fixed)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant = Tenant(name="Fallback", slug=f"fallback-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url=destination.original_url, paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("secret-value"))
    event = ProviderOutboxEvent(tenant_id=uuid4(), event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(), payload={}, idempotency_key="fallback-delivery")
    await _deliver(tenant, event)
    assert attempts == ["93.184.216.34", "93.184.216.35"]


@pytest.mark.asyncio
async def test_read_failure_does_not_try_second_ip(monkeypatch):
    from app.core.webhook_destination import ResolvedWebhookDestination
    destination = ResolvedWebhookDestination("https://hooks.example.com/path", "hooks.example.com", "hooks.example.com", ("93.184.216.34", "93.184.216.35"))

    async def fixed(_url): return destination
    attempts = []

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, _method, url, **_kwargs):
            attempts.append(url.host)
            raise httpx.ReadTimeout("read failed", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", fixed)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant = Tenant(name="Read failure", slug=f"read-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url=destination.original_url, paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("secret-value"))
    event = ProviderOutboxEvent(tenant_id=uuid4(), event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(), payload={}, idempotency_key="read-failure")
    with pytest.raises(ProviderDeliveryError):
        await _deliver(tenant, event)
    assert attempts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_pinned_tls_connection_preserves_sni_certificate_and_host(tmp_path, monkeypatch):
    hostname = "hooks.example.test"
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DB-002 Test CA")])
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    ca_cert = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now_naive - timedelta(days=1)).not_valid_after(now_naive + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    leaf_cert = (
        x509.CertificateBuilder().subject_name(leaf_name).issuer_name(ca_name)
        .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now_naive - timedelta(days=1)).not_valid_after(now_naive + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_path, cert_path, key_path = tmp_path / "ca.pem", tmp_path / "leaf.pem", tmp_path / "leaf.key"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))

    observed = {"sni": None, "request": b""}
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(cert_path), str(key_path))
    server_context.set_servername_callback(lambda _sock, server_name, _ctx: observed.update(sni=server_name))

    async def handler(reader, writer):
        observed["request"] = await reader.readuntil(b"\r\n\r\n")
        content_length = 0
        for line in observed["request"].split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                content_length = int(line.split(b":", 1)[1])
        if content_length:
            await reader.readexactly(content_length)
        writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain(); writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    from app.core.webhook_destination import ResolvedWebhookDestination
    original_url = f"https://{hostname}:{port}/conversion"
    destination = ResolvedWebhookDestination(original_url, hostname, f"{hostname}:{port}", ("127.0.0.1",))

    async def fixed(_url): return destination
    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", fixed)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", lambda **kwargs: real_client(verify=str(ca_path), **kwargs))
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant = Tenant(name="TLS pin", slug=f"tls-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url=original_url, paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("secret-value"))
    event = ProviderOutboxEvent(tenant_id=uuid4(), event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(), payload={}, idempotency_key="tls-pinned")
    try:
        assert await _deliver(tenant, event) == (None, 204)
    finally:
        server.close(); await server.wait_closed()
    assert observed["sni"] == hostname
    assert f"host: {hostname}:{port}".encode() in observed["request"].lower()


def test_timestamp_body_signature_has_replay_window():
    now = datetime.now(timezone.utc)
    timestamp = str(int(now.timestamp()))
    body = b'{"event":"paid"}'
    signature = f"sha256={conversion_signature('secret', timestamp, body)}"
    assert verify_conversion_signature(secret="secret", timestamp=timestamp, body=body, signature=signature, now=now)
    assert not verify_conversion_signature(secret="secret", timestamp=timestamp, body=body, signature=signature, now=now + timedelta(minutes=6), tolerance_seconds=300)
    assert not verify_conversion_signature(secret="secret", timestamp=timestamp, body=b"tampered", signature=signature, now=now)


def test_versioned_keyring_decrypts_old_and_reencrypts_to_active(monkeypatch):
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", "")
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS", json.dumps({"v1": old_key, "v2": new_key}))
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION", "v1")
    old_ciphertext = encrypt_paid_invoice_webhook_secret("signing-secret")
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION", "v2")
    assert decrypt_paid_invoice_webhook_secret(old_ciphertext) == "signing-secret"
    rotated = reencrypt_paid_invoice_webhook_secret(old_ciphertext)
    assert rotated.startswith("dbwh:v2:")
    assert decrypt_paid_invoice_webhook_secret(rotated) == "signing-secret"


@pytest.mark.asyncio
async def test_crypto_configuration_failure_does_not_consume_retry_or_disable(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.core.config.settings.PROVIDER_OUTBOX_MAX_ATTEMPTS", 1)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="Broken Key", slug=f"broken-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://hooks.example.com/path", paid_invoice_webhook_secret_encrypted="dbwh:missing:not-a-token")
        event = ProviderOutboxEvent(tenant=tenant, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(), payload={}, idempotency_key="broken-key", status=ProviderOutboxStatus.PENDING.value, available_at=datetime.now(timezone.utc))
        db.add_all([tenant, event]); await db.commit(); tenant_id, event_id = tenant.id, event.id

    async def public(_url):
        from app.core.webhook_destination import ResolvedWebhookDestination
        return ResolvedWebhookDestination("https://hooks.example.com/path", "hooks.example.com", "hooks.example.com", ("93.184.216.34",))
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", public)
    result = await process_due_paid_invoice_webhooks(session_factory=factory)
    assert result["configuration_blocked"] == 1
    async with factory() as db:
        tenant, event = await db.get(Tenant, tenant_id), await db.get(ProviderOutboxEvent, event_id)
        assert tenant.paid_invoice_webhook_enabled is True
        assert event.status == ProviderOutboxStatus.PENDING.value
        assert event.attempt_count == 0


@pytest.mark.asyncio
async def test_rotation_service_has_dry_run_and_apply(db_session, monkeypatch):
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", "")
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS", json.dumps({"v1": old_key, "v2": new_key}))
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION", "v1")
    tenant = Tenant(name="Rotate", slug=f"rotate-{uuid4().hex}", paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("secret"))
    db_session.add(tenant); await db_session.commit(); original = tenant.paid_invoice_webhook_secret_encrypted
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION", "v2")
    assert await rotate_paid_invoice_webhook_secrets(db_session, apply=False) == 1
    await db_session.refresh(tenant); assert tenant.paid_invoice_webhook_secret_encrypted == original
    assert await rotate_paid_invoice_webhook_secrets(db_session, apply=True) == 1
    await db_session.refresh(tenant); assert tenant.paid_invoice_webhook_secret_encrypted.startswith("dbwh:v2:")


@pytest.mark.asyncio
async def test_retention_and_customer_erasure_remove_payload_pii(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.CONVERSION_OUTBOX_PII_RETENTION_DAYS", 30)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as db:
        tenant = Tenant(name="Retention", slug=f"retention-{uuid4().hex}")
        customer = Customer(tenant=tenant, first_name="Private", last_name="Person", email="private@example.com")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}", status=RepairOrderStatus.PAID)
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("10"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("10"), paid_at=now)
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        old = ProviderOutboxEvent(tenant=tenant, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=invoice.id, payload={"event_id": str(uuid4()), "customer": {"email": "private@example.com"}, "attribution": {"landing_page_url": "https://x/?email=private@example.com"}, "service_lines": [{"name": "Private Person repair"}]}, idempotency_key="old", status=ProviderOutboxStatus.SUCCEEDED.value, available_at=now, completed_at=now - timedelta(days=31))
        current = ProviderOutboxEvent(tenant=tenant, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=invoice.id, payload={"event_id": str(uuid4()), "customer": {"email": "private@example.com"}}, idempotency_key="current", status=ProviderOutboxStatus.SUCCEEDED.value, available_at=now, completed_at=now)
        db.add_all([old, current]); await db.commit(); ids=(tenant.id, customer.id, old.id, current.id)
    assert await purge_expired_conversion_event_pii(session_factory=factory, now=now) == 1
    async with factory() as db:
        old = await db.get(ProviderOutboxEvent, ids[2]); current = await db.get(ProviderOutboxEvent, ids[3])
        assert "customer" not in old.payload and "attribution" not in old.payload and "service_lines" not in old.payload
        assert "customer" in current.payload
        assert await erase_customer_conversion_event_pii(db, tenant_id=ids[0], customer_id=ids[1], apply=True) == 1
        await db.refresh(current); assert "customer" not in current.payload


@pytest.mark.asyncio
async def test_ungranted_admin_is_denied_and_sensitive_actions_are_audited(db_session):
    tenant = Tenant(name="Permission", slug=f"permission-{uuid4().hex}")
    denied = User(tenant=tenant, email=f"denied-{uuid4().hex}@example.com", hashed_password="x", first_name="No", last_name="Grant", role=UserRole.GARAGE_ADMIN, is_active=True, is_verified=True, permissions={})
    granted = User(tenant=tenant, email=f"granted-{uuid4().hex}@example.com", hashed_password="x", first_name="Has", last_name="Grant", role=UserRole.GARAGE_ADMIN, is_active=True, is_verified=True, permissions={"conversion_exports": True})
    db_session.add_all([tenant, denied, granted]); await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        conversion_exports._require_conversion_access(denied)
    assert exc.value.status_code == 403
    settings_gate = admin.require_permission("conversion_exports")
    with pytest.raises(HTTPException) as exc:
        await settings_gate(current_user=denied)
    assert exc.value.status_code == 403
    assert await settings_gate(current_user=granted) is granted
    assert conversion_exports._require_conversion_access(granted) == tenant.id
    created = await conversion_exports.create_api_key(conversion_exports.ApiKeyCreate(name="Audit key"), db=db_session, user=granted)
    await conversion_exports.revoke_api_key(created.id, db=db_session, user=granted)
    audits = (await db_session.execute(select(ConversionExportAudit).order_by(ConversionExportAudit.created_at))).scalars().all()
    assert [row.action for row in audits] == ["api_key.created", "api_key.revoked"]
    assert all("api_key" not in row.metadata_json for row in audits)


def test_attribution_schema_lengths_match_database():
    from pydantic import ValidationError
    from app.schemas.repair_order import RepairOrderUpdate
    with pytest.raises(ValidationError):
        RepairOrderUpdate(lead_source_channel="x" * 65)
    with pytest.raises(ValidationError):
        RepairOrderUpdate(utm_campaign="x" * 256)
    with pytest.raises(ValidationError):
        RepairOrderUpdate(landing_page_url="x" * 2049)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("DB002_POSTGRES_URL"), reason="requires isolated PostgreSQL")
async def test_concurrent_correction_keys_serialize_on_invoice_row():
    engine = create_async_engine(os.environ["DB002_POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            tenant = Tenant(name="Concurrent", slug=f"concurrent-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://hooks.example.com/path", paid_invoice_webhook_secret_encrypted="encrypted")
            owner = User(tenant=tenant, email=f"owner-{uuid4().hex}@example.com", hashed_password="x", first_name="Owner", last_name="One", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
            customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email=f"customer-{uuid4().hex}@example.com")
            vehicle = Vehicle(tenant=tenant, customer=customer, make="Test", model="Truck")
            order = RepairOrder(tenant=tenant, customer=customer, vehicle=vehicle, order_number=f"RO-{uuid4().hex}", status=RepairOrderStatus.PAID)
            invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("100"), paid_at=datetime.now(timezone.utc))
            payment = Payment(tenant=tenant, invoice=invoice, payment_number=f"PAY-{uuid4().hex}", amount=Decimal("100"), method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED)
            db.add_all([tenant, owner, customer, vehicle, order, invoice, payment]); await db.commit()
            invoice_id, owner_id = invoice.id, owner.id

        async def correct(key):
            async with factory() as db:
                user = await db.get(User, owner_id)
                return await conversion_exports.create_correction(
                    invoice_id,
                    conversion_exports.CorrectionRequest(event_type="repair_order.payment_refunded", total_amount=Decimal("-60")),
                    idempotency_key=key, db=db, user=user,
                )

        results = await asyncio.gather(correct("concurrent-key-1"), correct("concurrent-key-2"), return_exceptions=True)
        assert len([result for result in results if isinstance(result, dict)]) == 1
        failures = [result for result in results if isinstance(result, HTTPException)]
        assert len(failures) == 1 and failures[0].status_code == 422
    finally:
        await engine.dispose()
