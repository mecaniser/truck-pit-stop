from __future__ import annotations

import pytest

from app.db.models.tenant import Tenant


LANDING_PARTNERS_URL = "/api/v1/auth/landing-partners"


@pytest.mark.asyncio
async def test_landing_partners_returns_only_active_approved_businesses(client, db_session):
    db_session.add_all(
        [
            Tenant(
                name="Bravo Diesel",
                slug="bravo-diesel",
                is_active=True,
                enrollment_status="approved",
                website="https://bravo.example.com",
                logo_url="https://cdn.example.com/bravo.png",
                partner_summary="Fast roadside repair support.",
                partner_services="Roadside repair, PM",
            ),
            Tenant(
                name="Atlas Fleet Service",
                slug="atlas-fleet-service",
                is_active=True,
                enrollment_status="approved",
                website="https://atlas.example.com",
                partner_summary="Heavy-duty diagnostics and mobile repair.",
            ),
            Tenant(
                name="Inactive Approved",
                slug="inactive-approved",
                is_active=False,
                enrollment_status="approved",
            ),
            Tenant(
                name="Pending Garage",
                slug="pending-garage",
                is_active=True,
                enrollment_status="pending",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(LANDING_PARTNERS_URL)

    assert response.status_code == 200
    body = response.json()
    assert [partner["name"] for partner in body] == ["Atlas Fleet Service", "Bravo Diesel"]
    assert body[0]["slug"] == "atlas-fleet-service"
    assert body[0]["partner_summary"] == "Heavy-duty diagnostics and mobile repair."
    assert body[1]["website"] == "https://bravo.example.com"
    assert body[1]["partner_services"] == "Roadside repair, PM"
