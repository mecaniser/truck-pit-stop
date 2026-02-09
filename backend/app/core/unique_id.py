"""
Unique ID generation utilities with retry logic for race condition handling.

This module provides robust unique number generation for entities like
repair orders, quotes, and invoices. It handles the rare case where
concurrent requests generate the same number by retrying with an
incremented value.
"""

from typing import Callable, TypeVar, Awaitable
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def generate_unique_number(
    db: AsyncSession,
    model_class,
    number_column,
    tenant_id: UUID,
    prefix: str,
) -> str:
    """
    Generate a unique sequential number for a tenant-scoped entity.
    
    Uses MAX of existing numbers to find the next available number,
    which is more reliable than COUNT when soft-deletes exist.
    
    Args:
        db: Database session
        model_class: SQLAlchemy model class (e.g., Quote, Invoice)
        number_column: The column containing the number (e.g., Quote.quote_number)
        tenant_id: Tenant UUID for scoping
        prefix: Number prefix (e.g., "Q-", "INV-", "RO-")
    
    Returns:
        Generated unique number string like "Q-2B45A36A-000011"
    """
    tenant_prefix = f"{prefix}{str(tenant_id).replace('-', '').upper()[:8]}-"
    
    # Get the highest existing number for this tenant
    result = await db.execute(
        select(func.max(number_column))
        .where(model_class.tenant_id == tenant_id)
        .where(number_column.like(f"{tenant_prefix}%"))
    )
    max_number = result.scalar()
    
    if max_number:
        # Extract the numeric suffix and increment
        try:
            current_num = int(max_number.split("-")[-1])
            next_num = current_num + 1
        except (ValueError, IndexError):
            # Fallback if parsing fails
            next_num = 1
    else:
        next_num = 1
    
    return f"{tenant_prefix}{next_num:06d}"


async def create_with_retry(
    db: AsyncSession,
    create_fn: Callable[[str], Awaitable[T]],
    generate_number_fn: Callable[[], Awaitable[str]],
    entity_name: str = "entity",
    max_retries: int = 3,
) -> T:
    """
    Create an entity with a unique number, retrying on collision.
    
    This handles the rare race condition where two concurrent requests
    generate the same number. Uses savepoints (nested transactions) so
    that on IntegrityError, only the failed insert is rolled back - not
    any prior work in the same transaction (e.g., customer/vehicle creation
    in quick_create_repair_order).
    
    Args:
        db: Database session
        create_fn: Async function that creates the entity given a number.
                   Should NOT call db.commit() - the savepoint handles it.
        generate_number_fn: Async function that generates the next number
        entity_name: Name for logging (e.g., "quote", "invoice")
        max_retries: Maximum retry attempts (default 3)
    
    Returns:
        The created entity
    
    Raises:
        IntegrityError: If all retries fail (extremely rare)
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            number = await generate_number_fn()
            
            # Use a savepoint so we only rollback this attempt, not the whole transaction
            async with db.begin_nested():
                result = await create_fn(number)
            
            # Commit the outer transaction after successful nested transaction
            await db.commit()
            
            if attempt > 0:
                logger.info(
                    f"{entity_name}_created_after_retry",
                    attempt=attempt + 1,
                    number=number,
                )
            
            return result
            
        except IntegrityError as e:
            last_error = e
            error_str = str(e)
            
            # Only retry if it's a unique constraint violation on the number
            if "unique" in error_str.lower() and "number" in error_str.lower():
                # Savepoint automatically rolled back, no need for explicit rollback
                logger.warning(
                    f"{entity_name}_number_collision",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=error_str[:200],
                )
                
                if attempt < max_retries - 1:
                    continue
            
            # Re-raise if it's a different integrity error or max retries reached
            raise
    
    # Should never reach here, but just in case
    raise last_error  # type: ignore
