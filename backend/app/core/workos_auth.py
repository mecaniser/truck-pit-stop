"""WorkOS principal helpers used during the additive authentication cutover."""
from dataclasses import dataclass
from typing import FrozenSet
from uuid import UUID

from fastapi import HTTPException, status


@dataclass(frozen=True)
class CurrentPrincipal:
    local_user_id: UUID
    workos_user_id: str
    workos_org_id: str
    tenant_id: UUID
    permissions: FrozenSet[str]


def require_permission(*required: str):
    """Return a principal guard; callers still enforce record ownership."""
    required_set = frozenset(required)

    def check(principal: CurrentPrincipal) -> CurrentPrincipal:
        if not required_set.issubset(principal.permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required permission",
            )
        return principal

    return check
