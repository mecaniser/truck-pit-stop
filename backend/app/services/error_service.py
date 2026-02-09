"""
Error Service for persistent error logging and querying.

Provides methods to log errors to the database and query them for the admin dashboard.
"""
import traceback
from datetime import datetime, timedelta
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.error_log import ErrorLog, ErrorCategory, ErrorSeverity
from app.db.session import AsyncSessionLocal


# Sensitive fields to strip from request context
SENSITIVE_FIELDS = {
    "password", "token", "secret", "api_key", "apikey", "authorization",
    "cookie", "session", "credit_card", "card_number", "cvv", "ssn",
    "hashed_password", "access_token", "refresh_token"
}


def sanitize_context(data: dict) -> dict:
    """Remove sensitive fields from request context."""
    if not data:
        return {}
    
    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_context(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_context(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


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
    db: Optional[AsyncSession] = None,
) -> Optional[ErrorLog]:
    """
    Log an error to the database.
    
    If no db session is provided, creates a new one (for use in exception handlers).
    """
    try:
        # Create new session if not provided
        close_session = False
        if db is None:
            db = AsyncSessionLocal()
            close_session = True
        
        error_log = ErrorLog(
            error_type=error_type,
            message=message[:10000] if message else "No message",  # Truncate very long messages
            error_category=category.value if hasattr(category, 'value') else category,
            severity=severity.value if hasattr(severity, 'value') else severity,
            correlation_id=correlation_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            user_id=user_id,
            tenant_id=tenant_id,
            stack_trace=stack_trace[:50000] if stack_trace else None,  # Truncate very long traces
            request_context=sanitize_context(request_context) if request_context else None,
        )
        
        db.add(error_log)
        await db.commit()
        await db.refresh(error_log)
        
        if close_session:
            await db.close()
        
        return error_log
    except Exception as e:
        # Don't let error logging failures break the app
        # Log to stdout as fallback
        import structlog
        logger = structlog.get_logger()
        logger.error(
            "failed_to_persist_error",
            original_error=message,
            persistence_error=str(e),
        )
        return None


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
    db: Optional[AsyncSession] = None,
) -> Optional[ErrorLog]:
    """Log an error from an exception object."""
    return await log_error(
        error_type=type(exc).__name__,
        message=str(exc),
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
        db=db,
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
) -> list[ErrorLog]:
    """Find all errors with the same correlation ID."""
    result = await db.execute(
        select(ErrorLog)
        .where(
            ErrorLog.correlation_id == correlation_id,
            ErrorLog.deleted_at.is_(None)
        )
        .order_by(ErrorLog.created_at)
    )
    return list(result.scalars().all())


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
