"""
Error Service for persistent error logging and querying.

Provides methods to log errors to the database and query them for the admin dashboard.
"""
import asyncio
import ipaddress
import re
import traceback
import weakref
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.correlation import normalize_optional_correlation_id
from app.core.logging import get_logger
from app.core.redaction import redact_sensitive, redact_text
from app.db.models.error_log import ErrorLog, ErrorCategory, ErrorSeverity
from app.db.session import AsyncSessionLocal


logger = get_logger(__name__)

ERROR_TYPE_MAX_LENGTH = 255
ERROR_MESSAGE_MAX_LENGTH = 10_000
ERROR_STACK_MAX_LENGTH = 50_000
# The database column is 500 characters; this is stricter than the 512-character
# architecture ceiling and avoids a persistence failure at the boundary.
ERROR_ENDPOINT_MAX_LENGTH = 500
ERROR_METHOD_MAX_LENGTH = 10
ERROR_CLIENT_MAX_LENGTH = 64
ERROR_LOG_WORK_FRACTION = 0.45
ERROR_LOG_PHASE_GRACE_FRACTION = 0.12
ERROR_LOG_MAX_PHASE_CANCEL_WAVES = 2
_SAFE_CLIENT_LABEL = re.compile(r"\A[A-Za-z0-9._:-]{1,64}\Z")
_SENSITIVE_ROUTE_SEGMENT = re.compile(
    r"(?i)(/(?:api/v1/)?(?:quotes/token|invoice-access/pdf|quote|invoice)/)[^/]+"
)

@dataclass(frozen=True, slots=True)
class ErrorPersistenceEnvelope:
    """Immutable, request-free input retained by exception background work."""

    error_type: str
    message: str
    category: str
    severity: str
    correlation_id: Optional[str]
    endpoint: Optional[str]
    method: Optional[str]
    status_code: Optional[int]
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    stack_trace: Optional[str]
    client_ip: Optional[str]


def _bounded_redacted_text(
    value: Any,
    *,
    limit: int,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if value is None:
        return fallback
    rendered = redact_text(str(value)).strip()
    if not rendered:
        return fallback
    return rendered[:limit]


def _normalized_uuid(value: Any) -> Optional[UUID]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _normalized_status_code(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 100 <= value <= 599 else None


def normalize_error_endpoint(value: Any) -> Optional[str]:
    """Return a path-only endpoint with known credential segments replaced."""

    if value is None:
        return None
    rendered = str(value)
    parsed = urlsplit(rendered)
    path = parsed.path if parsed.scheme or parsed.netloc else rendered.partition("?")[0]
    path = path.partition("#")[0]
    sanitized = _SENSITIVE_ROUTE_SEGMENT.sub(r"\1:token", path)
    return _bounded_redacted_text(
        sanitized,
        limit=ERROR_ENDPOINT_MAX_LENGTH,
    )


def _normalized_method(value: Any) -> Optional[str]:
    method = _bounded_redacted_text(
        value,
        limit=ERROR_METHOD_MAX_LENGTH,
    )
    if method is None:
        return None
    method = method.upper()
    return method if method.isascii() and method.isalpha() else None


def _normalized_client(value: Any) -> Optional[str]:
    if value is None:
        return None
    rendered = redact_text(str(value)).strip()[:ERROR_CLIENT_MAX_LENGTH]
    try:
        return str(ipaddress.ip_address(rendered))
    except ValueError:
        return rendered if _SAFE_CLIENT_LABEL.fullmatch(rendered) else None


def fallback_error_persistence_envelope(
    *,
    correlation_id: Any = None,
    status_code: Any = 500,
) -> ErrorPersistenceEnvelope:
    """Return a fixed credential-free record when snapshot creation fails."""

    return ErrorPersistenceEnvelope(
        error_type="ErrorSnapshotFailure",
        message="Error details unavailable",
        category=ErrorCategory.UNHANDLED.value,
        severity=ErrorSeverity.ERROR.value,
        correlation_id=normalize_optional_correlation_id(correlation_id),
        endpoint=None,
        method=None,
        status_code=_normalized_status_code(status_code),
        user_id=None,
        tenant_id=None,
        stack_trace=None,
        client_ip=None,
    )


def build_error_persistence_envelope(
    *,
    error_type: Any,
    message: Any,
    category: Any,
    severity: Any,
    correlation_id: Any,
    endpoint: Any,
    method: Any,
    status_code: Any,
    user_id: Any = None,
    tenant_id: Any = None,
    stack_trace: Any = None,
    client_ip: Any = None,
) -> ErrorPersistenceEnvelope:
    """Synchronously sanitize primitives before any background task is built."""

    try:
        category_value = (
            category.value if isinstance(category, ErrorCategory) else ErrorCategory(category).value
        )
        severity_value = (
            severity.value if isinstance(severity, ErrorSeverity) else ErrorSeverity(severity).value
        )
        return ErrorPersistenceEnvelope(
            error_type=_bounded_redacted_text(
                error_type,
                limit=ERROR_TYPE_MAX_LENGTH,
                fallback="UnknownError",
            )
            or "UnknownError",
            message=_bounded_redacted_text(
                message,
                limit=ERROR_MESSAGE_MAX_LENGTH,
                fallback="No message",
            )
            or "No message",
            category=category_value,
            severity=severity_value,
            correlation_id=normalize_optional_correlation_id(correlation_id),
            endpoint=normalize_error_endpoint(endpoint),
            method=_normalized_method(method),
            status_code=_normalized_status_code(status_code),
            user_id=_normalized_uuid(user_id),
            tenant_id=_normalized_uuid(tenant_id),
            stack_trace=_bounded_redacted_text(
                stack_trace,
                limit=ERROR_STACK_MAX_LENGTH,
            ),
            client_ip=_normalized_client(client_ip),
        )
    except Exception:
        return fallback_error_persistence_envelope(
            correlation_id=correlation_id,
            status_code=status_code,
        )

# Test runners can create a fresh event loop per test. Keep the concurrency
# guard per loop instead of binding one asyncio semaphore to whichever loop
# happens to log the first error.
_persistence_semaphores: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.BoundedSemaphore
] = weakref.WeakKeyDictionary()


def _persistence_semaphore() -> asyncio.BoundedSemaphore:
    loop = asyncio.get_running_loop()
    semaphore = _persistence_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.BoundedSemaphore(settings.ERROR_LOG_PERSIST_MAX_CONCURRENCY)
        _persistence_semaphores[loop] = semaphore
    return semaphore


def sanitize_context(data: dict) -> dict:
    """Recursively remove sensitive fields and URL-embedded credentials."""
    if not data:
        return {}
    return redact_sensitive(data)


@dataclass(slots=True)
class _PersistenceLifecycleState:
    phase: str = "pending"
    generation: int = 0
    phase_started_at: float = 0.0
    in_cleanup: bool = False

    def begin(self, phase: str, *, cleanup: bool) -> None:
        self.phase = phase
        self.generation += 1
        self.phase_started_at = asyncio.get_running_loop().time()
        self.in_cleanup = cleanup


def _consume_task_result(task: asyncio.Future) -> None:
    try:
        task.result()
    except BaseException:
        pass


async def _cleanup_session_call(
    session: Any,
    method_name: str,
    *,
    state: _PersistenceLifecycleState,
) -> tuple[bool, Optional[asyncio.CancelledError]]:
    method = getattr(session, method_name, None)
    if method is None:
        return False, None
    state.begin(f"cleanup:{method_name}", cleanup=True)
    try:
        await method()
        return True, None
    except asyncio.CancelledError as exc:
        return False, exc
    except Exception:
        return False, None


async def _owned_error_lifecycle(
    error_log: ErrorLog,
    *,
    stop_requested: asyncio.Event,
    state: _PersistenceLifecycleState,
) -> Optional[ErrorLog]:
    """Own the permit, session, write, and cleanup as one indivisible lifecycle."""

    semaphore = _persistence_semaphore()
    permit_acquired = False
    session: Any = None
    commit_started = False
    commit_confirmed = False
    operation_succeeded = False
    cleanup_succeeded = False
    failure_phase = "stopped"
    cancellation: Optional[asyncio.CancelledError] = None

    try:
        state.begin("acquire", cleanup=False)
        try:
            await semaphore.acquire()
            permit_acquired = True
            # Establish ownership before accepting a cancellation delivered on
            # the exact loop turn that completed semaphore acquisition.
            await asyncio.sleep(0)
        except asyncio.CancelledError as exc:
            cancellation = exc

        if permit_acquired and cancellation is None:
            try:
                if not stop_requested.is_set():
                    state.begin("session", cleanup=False)
                    failure_phase = "session"
                    session = AsyncSessionLocal()

                if session is not None and not stop_requested.is_set():
                    state.begin("add", cleanup=False)
                    failure_phase = "add"
                    session.add(error_log)

                if session is not None and not stop_requested.is_set():
                    state.begin("commit", cleanup=False)
                    failure_phase = "commit"
                    commit_started = True
                    await session.commit()
                    commit_confirmed = True

                # A late commit can be confirmed after a cutoff, but no new
                # persistence operation may begin once the controller stops work.
                if (
                    session is not None
                    and commit_confirmed
                    and not stop_requested.is_set()
                ):
                    state.begin("refresh", cleanup=False)
                    failure_phase = "refresh"
                    await session.refresh(error_log)
                    operation_succeeded = True
                    failure_phase = "complete"
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
            except Exception:
                pass
            finally:
                cleanup_cancellation: Optional[asyncio.CancelledError] = None

                if session is None:
                    cleanup_succeeded = True
                elif commit_started and not commit_confirmed:
                    # A started commit has an unknown outcome after any failure
                    # or cancellation. Invalidate exactly once and never issue
                    # rollback, close, refresh, retry, or another commit.
                    cleanup_succeeded, cleanup_cancellation = (
                        await _cleanup_session_call(
                            session,
                            "invalidate",
                            state=state,
                        )
                    )
                elif commit_confirmed:
                    # Confirmed commits are closed only. Failure or cancellation
                    # falls back to one invalidate without rollback or retry.
                    cleanup_succeeded, cleanup_cancellation = (
                        await _cleanup_session_call(
                            session,
                            "close",
                            state=state,
                        )
                    )
                    if not cleanup_succeeded:
                        cleanup_succeeded, invalidate_cancellation = (
                            await _cleanup_session_call(
                                session,
                                "invalidate",
                                state=state,
                            )
                        )
                        cleanup_cancellation = (
                            cleanup_cancellation or invalidate_cancellation
                        )
                else:
                    # Before commit, rollback then close. Any failed/cancelled
                    # cleanup step falls back to one invalidate.
                    rolled_back, rollback_cancellation = (
                        await _cleanup_session_call(
                            session,
                            "rollback",
                            state=state,
                        )
                    )
                    cleanup_cancellation = rollback_cancellation
                    if rolled_back:
                        cleanup_succeeded, close_cancellation = (
                            await _cleanup_session_call(
                                session,
                                "close",
                                state=state,
                            )
                        )
                        cleanup_cancellation = (
                            cleanup_cancellation or close_cancellation
                        )
                    if not rolled_back or not cleanup_succeeded:
                        cleanup_succeeded, invalidate_cancellation = (
                            await _cleanup_session_call(
                                session,
                                "invalidate",
                                state=state,
                            )
                        )
                        cleanup_cancellation = (
                            cleanup_cancellation or invalidate_cancellation
                        )

                cancellation = cancellation or cleanup_cancellation

        if cancellation is not None:
            raise cancellation
        if not operation_succeeded or not cleanup_succeeded:
            logger.warning("error_log_persistence_failed", phase=failure_phase)
            return None
        return error_log
    finally:
        if permit_acquired:
            semaphore.release()
        state.begin("settled", cleanup=False)


async def log_error(
    error_type: str,
    message: str,
    category: ErrorCategory = ErrorCategory.UNHANDLED,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    correlation_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    stack_trace: Optional[str] = None,
    request_context: Optional[dict] = None,
) -> Optional[ErrorLog]:
    """Persist one sanitized error through a dedicated, bounded lifecycle."""

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    total_budget = float(settings.ERROR_LOG_PERSIST_TIMEOUT_SECONDS)
    work_deadline = started_at + (total_budget * ERROR_LOG_WORK_FRACTION)
    hard_deadline = started_at + total_budget
    phase_grace = max(total_budget * ERROR_LOG_PHASE_GRACE_FRACTION, 0.001)

    envelope = build_error_persistence_envelope(
        error_type=error_type,
        message=message,
        category=category,
        severity=severity,
        correlation_id=correlation_id,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        user_id=user_id,
        tenant_id=tenant_id,
        stack_trace=stack_trace,
        client_ip=(request_context or {}).get("client_ip")
        if isinstance(request_context, dict)
        else None,
    )
    try:
        safe_request_context = (
            sanitize_context(request_context)
            if isinstance(request_context, dict) and request_context
            else None
        )
    except Exception:
        safe_request_context = None
    error_log = ErrorLog(
        error_type=envelope.error_type,
        message=envelope.message,
        error_category=envelope.category,
        severity=envelope.severity,
        correlation_id=envelope.correlation_id,
        endpoint=envelope.endpoint,
        method=envelope.method,
        status_code=envelope.status_code,
        user_id=envelope.user_id,
        tenant_id=envelope.tenant_id,
        stack_trace=envelope.stack_trace,
        request_context=safe_request_context,
    )

    stop_requested = asyncio.Event()
    state = _PersistenceLifecycleState()
    lifecycle = asyncio.create_task(
        _owned_error_lifecycle(
            error_log,
            stop_requested=stop_requested,
            state=state,
        ),
        name="error-persistence-lifecycle",
    )
    external_cancellation: Optional[asyncio.CancelledError] = None
    observed_generation = -1
    phase_cancellation_waves = 0
    next_phase_cancellation = work_deadline

    while not lifecycle.done():
        now = loop.time()
        if now >= hard_deadline:
            break

        if state.generation != observed_generation:
            observed_generation = state.generation
            phase_cancellation_waves = 0
            if state.in_cleanup:
                next_phase_cancellation = state.phase_started_at + phase_grace
            elif stop_requested.is_set():
                next_phase_cancellation = now
            else:
                next_phase_cancellation = work_deadline

        if not stop_requested.is_set() and now >= work_deadline:
            stop_requested.set()
            next_phase_cancellation = now

        if (
            stop_requested.is_set()
            and now >= next_phase_cancellation
            and phase_cancellation_waves < ERROR_LOG_MAX_PHASE_CANCEL_WAVES
            and not lifecycle.done()
        ):
            lifecycle.cancel()
            phase_cancellation_waves += 1
            next_phase_cancellation = now + phase_grace

        if lifecycle.done():
            break

        if stop_requested.is_set():
            wake_at = (
                next_phase_cancellation
                if phase_cancellation_waves < ERROR_LOG_MAX_PHASE_CANCEL_WAVES
                else hard_deadline
            )
        else:
            wake_at = work_deadline
        wait_for = max(0.0, min(wake_at, hard_deadline) - loop.time())

        try:
            await asyncio.wait({lifecycle}, timeout=wait_for)
        except asyncio.CancelledError as exc:
            if external_cancellation is None:
                external_cancellation = exc
            stop_requested.set()

            # External cancellation is the first wave for the currently-owned
            # phase. The controller keeps waiting so cleanup and permit release
            # can settle within the same hard deadline.
            if state.generation != observed_generation:
                observed_generation = state.generation
                phase_cancellation_waves = 0
            if (
                phase_cancellation_waves < ERROR_LOG_MAX_PHASE_CANCEL_WAVES
                and not lifecycle.done()
            ):
                lifecycle.cancel()
                phase_cancellation_waves += 1
                next_phase_cancellation = loop.time() + phase_grace

    if lifecycle.done():
        try:
            result = lifecycle.result()
        except BaseException:
            result = None
    else:
        # The driver resisted both cancellation waves. The lifecycle—not this
        # controller—continues to own the sanitized row, session, and permit.
        # When it eventually settles, its async semaphore scope restores capacity.
        lifecycle.add_done_callback(_consume_task_result)
        result = None

    if external_cancellation is not None:
        raise external_cancellation
    return result


async def persist_error_envelope(
    envelope: ErrorPersistenceEnvelope,
) -> Optional[ErrorLog]:
    """Persist one pre-sanitized request-free exception snapshot."""

    request_context = (
        {"client_ip": envelope.client_ip}
        if envelope.client_ip is not None
        else None
    )
    return await log_error(
        error_type=envelope.error_type,
        message=envelope.message,
        category=envelope.category,
        severity=envelope.severity,
        correlation_id=envelope.correlation_id,
        endpoint=envelope.endpoint,
        method=envelope.method,
        status_code=envelope.status_code,
        user_id=envelope.user_id,
        tenant_id=envelope.tenant_id,
        stack_trace=envelope.stack_trace,
        request_context=request_context,
    )


async def log_error_from_exception(
    exc: Exception,
    category: ErrorCategory = ErrorCategory.UNHANDLED,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    correlation_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    request_context: Optional[dict] = None,
) -> Optional[ErrorLog]:
    """Log an error from an exception object via a dedicated owned session."""

    return await log_error(
        error_type=type(exc).__name__,
        message=exc,
        category=category,
        severity=severity,
        correlation_id=correlation_id,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        user_id=user_id,
        tenant_id=tenant_id,
        stack_trace=traceback.format_exc(),
        request_context=request_context,
    )


async def get_errors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    error_type: Optional[str] = None,
    category: Optional[ErrorCategory] = None,
    severity: Optional[ErrorSeverity] = None,
    endpoint: Optional[str] = None,
    user_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    resolved: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
) -> tuple[list[ErrorLog], int]:
    """
    Query errors with filters and pagination.
    
    Returns tuple of (errors, total_count).
    """
    query = select(ErrorLog).where(ErrorLog.deleted_at.is_(None))
    count_query = select(func.count(ErrorLog.id)).where(ErrorLog.deleted_at.is_(None))
    
    # Apply filters
    filters = []
    
    if error_type:
        filters.append(ErrorLog.error_type == error_type)
    
    if category:
        filters.append(ErrorLog.error_category == category.value)
    
    if severity:
        filters.append(ErrorLog.severity == severity.value)
    
    if endpoint:
        filters.append(ErrorLog.endpoint.ilike(f"%{endpoint}%"))
    
    if user_id:
        filters.append(ErrorLog.user_id == user_id)
    
    if tenant_id:
        filters.append(ErrorLog.tenant_id == tenant_id)
    
    if resolved is not None:
        filters.append(ErrorLog.resolved == resolved)
    
    if start_date:
        filters.append(ErrorLog.created_at >= start_date)
    
    if end_date:
        filters.append(ErrorLog.created_at <= end_date)
    
    if search:
        search_filter = or_(
            ErrorLog.message.ilike(f"%{search}%"),
            ErrorLog.error_type.ilike(f"%{search}%"),
            ErrorLog.correlation_id.ilike(f"%{search}%"),
        )
        filters.append(search_filter)
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = query.order_by(desc(ErrorLog.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    errors = result.scalars().all()
    
    return list(errors), total


async def get_error_by_id(db: AsyncSession, error_id: UUID) -> Optional[ErrorLog]:
    """Get a single error by ID."""
    result = await db.execute(
        select(ErrorLog).where(
            ErrorLog.id == error_id,
            ErrorLog.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def get_errors_by_correlation_id(
    db: AsyncSession,
    correlation_id: str,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[ErrorLog], int]:
    """Find errors by correlation ID with pagination."""
    where_clause = and_(
        ErrorLog.correlation_id == correlation_id,
        ErrorLog.deleted_at.is_(None),
    )

    total_result = await db.execute(
        select(func.count(ErrorLog.id)).where(where_clause)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(ErrorLog)
        .where(where_clause)
        .order_by(ErrorLog.created_at)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def resolve_error(
    db: AsyncSession,
    error_id: UUID,
    resolved_by_id: UUID,
    notes: Optional[str] = None,
) -> Optional[ErrorLog]:
    """Mark an error as resolved."""
    error = await get_error_by_id(db, error_id)
    if not error:
        return None
    
    error.resolved = True
    error.resolved_at = datetime.utcnow()
    error.resolved_by_id = resolved_by_id
    if notes:
        error.notes = notes
    
    await db.commit()
    await db.refresh(error)
    return error


async def unresolve_error(db: AsyncSession, error_id: UUID) -> Optional[ErrorLog]:
    """Mark an error as unresolved (reopen)."""
    error = await get_error_by_id(db, error_id)
    if not error:
        return None
    
    error.resolved = False
    error.resolved_at = None
    error.resolved_by_id = None
    
    await db.commit()
    await db.refresh(error)
    return error


async def get_error_stats(
    db: AsyncSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Get aggregated error statistics for the dashboard.
    """
    # Default to last 24 hours if no dates provided
    if not start_date:
        start_date = datetime.utcnow() - timedelta(hours=24)
    if not end_date:
        end_date = datetime.utcnow()
    
    base_filter = and_(
        ErrorLog.deleted_at.is_(None),
        ErrorLog.created_at >= start_date,
        ErrorLog.created_at <= end_date,
    )
    
    # Total errors
    total_result = await db.execute(
        select(func.count(ErrorLog.id)).where(base_filter)
    )
    total = total_result.scalar() or 0
    
    # Unresolved errors
    unresolved_result = await db.execute(
        select(func.count(ErrorLog.id)).where(
            base_filter,
            ErrorLog.resolved == False
        )
    )
    unresolved = unresolved_result.scalar() or 0
    
    # By category
    category_result = await db.execute(
        select(ErrorLog.error_category, func.count(ErrorLog.id))
        .where(base_filter)
        .group_by(ErrorLog.error_category)
    )
    by_category = {str(row[0]) if row[0] else "unknown": row[1] for row in category_result.all()}
    
    # By severity
    severity_result = await db.execute(
        select(ErrorLog.severity, func.count(ErrorLog.id))
        .where(base_filter)
        .group_by(ErrorLog.severity)
    )
    by_severity = {str(row[0]) if row[0] else "unknown": row[1] for row in severity_result.all()}
    
    # Top error types
    type_result = await db.execute(
        select(ErrorLog.error_type, func.count(ErrorLog.id).label("count"))
        .where(base_filter)
        .group_by(ErrorLog.error_type)
        .order_by(desc("count"))
        .limit(10)
    )
    top_types = [{"type": row[0], "count": row[1]} for row in type_result.all()]
    
    # Top endpoints
    endpoint_result = await db.execute(
        select(ErrorLog.endpoint, func.count(ErrorLog.id).label("count"))
        .where(base_filter, ErrorLog.endpoint.isnot(None))
        .group_by(ErrorLog.endpoint)
        .order_by(desc("count"))
        .limit(10)
    )
    top_endpoints = [{"endpoint": row[0], "count": row[1]} for row in endpoint_result.all()]
    
    # Critical errors (last 24h)
    critical_result = await db.execute(
        select(func.count(ErrorLog.id)).where(
            base_filter,
            ErrorLog.severity == ErrorSeverity.CRITICAL.value
        )
    )
    critical_count = critical_result.scalar() or 0
    
    return {
        "total": total,
        "unresolved": unresolved,
        "critical": critical_count,
        "by_category": by_category,
        "by_severity": by_severity,
        "top_error_types": top_types,
        "top_endpoints": top_endpoints,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        }
    }


async def get_distinct_error_types(db: AsyncSession) -> list[str]:
    """Get list of distinct error types for filtering."""
    result = await db.execute(
        select(ErrorLog.error_type)
        .where(ErrorLog.deleted_at.is_(None))
        .distinct()
        .order_by(ErrorLog.error_type)
    )
    return [row[0] for row in result.all() if row[0]]


async def get_distinct_endpoints(db: AsyncSession) -> list[str]:
    """Get list of distinct endpoints for filtering."""
    result = await db.execute(
        select(ErrorLog.endpoint)
        .where(ErrorLog.deleted_at.is_(None), ErrorLog.endpoint.isnot(None))
        .distinct()
        .order_by(ErrorLog.endpoint)
    )
    return [row[0] for row in result.all() if row[0]]
