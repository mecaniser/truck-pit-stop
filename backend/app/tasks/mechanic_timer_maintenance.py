"""
Mechanic timer maintenance task.

Runs every 5 minutes to:
1) Strictly auto-stop active timer sessions that crossed tenant-local midnight.
2) Strictly auto-end active break and attendance sessions at tenant-local midnight.
3) Evaluate idle streak alerts (one alert per streak).
"""
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select

from app.core.websocket import (
    broadcast_mechanic_attendance_update,
    broadcast_mechanic_break_update,
    broadcast_mechanic_idle_alert,
    broadcast_mechanic_timer_update,
)
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal
from app.services.pending_zelle_staff_notification_service import collect_staff_contacts
from app.services.twilio_service import send_sms
from app.services.mechanic_time_service import (
    close_attendance_crossing_midnight,
    close_breaks_crossing_midnight,
    close_sessions_crossing_midnight,
    evaluate_idle_alerts,
)
from app.tasks import celery_app


async def _process_mechanic_timer_maintenance(tenant_id: str | None = None) -> dict:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)

        closed_sessions = await close_sessions_crossing_midnight(db, now_utc=now)
        closed_breaks = await close_breaks_crossing_midnight(db, now_utc=now)
        closed_attendance = await close_attendance_crossing_midnight(db, now_utc=now)
        alerts = await evaluate_idle_alerts(db, now_utc=now, threshold_minutes=30)

        if tenant_id:
            closed_sessions = [s for s in closed_sessions if str(s.tenant_id) == tenant_id]
            closed_breaks = [s for s in closed_breaks if str(s.tenant_id) == tenant_id]
            closed_attendance = [s for s in closed_attendance if str(s.tenant_id) == tenant_id]
            alerts = [a for a in alerts if a["tenant_id"] == tenant_id]

        closed_payload = [
            {
                "tenant_id": str(s.tenant_id),
                "mechanic_id": str(s.mechanic_id),
                "session_id": str(s.id),
            }
            for s in closed_sessions
        ]
        closed_break_payload = [
            {
                "tenant_id": str(s.tenant_id),
                "mechanic_id": str(s.mechanic_id),
                "break_session_id": str(s.id),
            }
            for s in closed_breaks
        ]
        closed_attendance_payload = [
            {
                "tenant_id": str(s.tenant_id),
                "mechanic_id": str(s.mechanic_id),
                "attendance_session_id": str(s.id),
            }
            for s in closed_attendance
        ]
        alert_payload = list(alerts)

        await db.commit()

        for row in closed_payload:
            try:
                await broadcast_mechanic_timer_update(
                    tenant_id=row["tenant_id"],
                    mechanic_id=row["mechanic_id"],
                    session_id=row["session_id"],
                    action="auto_midnight_stop",
                )
            except Exception:
                pass

        for row in closed_break_payload:
            try:
                await broadcast_mechanic_break_update(
                    tenant_id=row["tenant_id"],
                    mechanic_id=row["mechanic_id"],
                    break_session_id=row["break_session_id"],
                    action="auto_midnight_end",
                )
            except Exception:
                pass

        for row in closed_attendance_payload:
            try:
                await broadcast_mechanic_attendance_update(
                    tenant_id=row["tenant_id"],
                    mechanic_id=row["mechanic_id"],
                    attendance_session_id=row["attendance_session_id"],
                    action="auto_midnight_clock_out",
                )
            except Exception:
                pass

        for row in alert_payload:
            try:
                await broadcast_mechanic_idle_alert(
                    tenant_id=row["tenant_id"],
                    mechanic_id=row["mechanic_id"],
                    idle_minutes=row["idle_minutes"],
                    local_date=row["local_date"],
                    mechanic_name=row.get("mechanic_name"),
                )
            except Exception:
                pass

            # Best-effort SMS alert to mechanic + owner/admin
            try:
                tenant_uuid = UUID(row["tenant_id"])
                mechanic_uuid = UUID(row["mechanic_id"])
                _, staff_phones = await collect_staff_contacts(db, tenant_uuid)
                mech_result = await db.execute(
                    select(User).where(
                        and_(
                            User.id == mechanic_uuid,
                            User.tenant_id == tenant_uuid,
                            User.role == UserRole.MECHANIC,
                        )
                    )
                )
                mechanic = mech_result.scalar_one_or_none()
                phones = set(staff_phones)
                if mechanic and mechanic.phone:
                    phones.add(mechanic.phone)
                sms_body = (
                    f"Idle alert: {row['mechanic_name']} has no active timer for "
                    f"{row['idle_minutes']} minutes during core hours. "
                    f"Date: {row['local_date']}."
                )
                for phone in phones:
                    try:
                        await send_sms(
                            db=db,
                            tenant_id=row["tenant_id"],
                            to=phone,
                            body=sms_body,
                            template_name="mechanic_idle_alert_sms",
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        return {
            "closed_sessions": len(closed_payload),
            "closed_breaks": len(closed_break_payload),
            "closed_attendance": len(closed_attendance_payload),
            "idle_alerts": len(alert_payload),
        }


@celery_app.task(name="process_mechanic_timer_maintenance")
def process_mechanic_timer_maintenance():
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(_process_mechanic_timer_maintenance())
        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
