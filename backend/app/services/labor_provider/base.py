from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class LaborProviderError(Exception):
    """Raised when provider data cannot be retrieved."""


@dataclass
class VehicleContext:
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None


@dataclass
class ProviderWarning:
    code: str
    message: str


@dataclass
class RepairOperationCandidate:
    operation_id: str
    name: str
    description: Optional[str]
    estimated_hours: Decimal
    provider: str = "motor"


@dataclass
class ProviderEstimate:
    operation_id: str
    name: str
    description: Optional[str]
    estimated_hours: Decimal
    warnings: list[ProviderWarning]


@dataclass
class ProviderPartSuggestion:
    part_number: str
    name: str
    quantity: int = 1


class LaborProvider(ABC):
    @abstractmethod
    async def search_operations(
        self,
        vehicle: VehicleContext,
        query: str,
    ) -> tuple[list[RepairOperationCandidate], list[ProviderWarning]]:
        raise NotImplementedError

    @abstractmethod
    async def get_operation_estimate(
        self,
        vehicle: VehicleContext,
        operation_id: str,
    ) -> ProviderEstimate:
        raise NotImplementedError

    @abstractmethod
    async def get_operation_parts(
        self,
        vehicle: VehicleContext,
        operation_id: str,
    ) -> tuple[list[ProviderPartSuggestion], list[ProviderWarning]]:
        raise NotImplementedError
