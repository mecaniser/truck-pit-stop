"""Create a large synthetic tenant for an isolated performance environment.

This command is intentionally unusable in production. It creates no external
provider records and must be given both an explicit environment and confirmation
phrase before it writes any data.
"""
import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.session import AsyncSessionLocal

CONFIRMATION = "seed-performance-data"
ALLOWED_ENVIRONMENTS = {"performance", "development", "test"}


def _validate_environment() -> None:
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            "Refusing to seed. ENVIRONMENT must be one of: "
            f"{', '.join(sorted(ALLOWED_ENVIRONMENTS))}."
        )
    if os.getenv("LOAD_TEST_SEED_CONFIRM") != CONFIRMATION:
        raise RuntimeError(
            "Refusing to seed. Set LOAD_TEST_SEED_CONFIRM="
            f"{CONFIRMATION!r} to acknowledge the destructive data creation."
        )


def _vin(number: int) -> str:
    return f"P{number:016d}"[-17:]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="performance-lab")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-password", required=True)
    parser.add_argument("--customers", type=int, default=150)
    parser.add_argument("--fleet-vehicles", type=int, default=120)
    parser.add_argument("--repair-orders", type=int, default=2500)
    parser.add_argument("--inventory-items", type=int, default=600)
    return parser.parse_args()


def _positive(name: str, value: int) -> int:
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


async def seed(args: argparse.Namespace) -> None:
    _validate_environment()
    for name in ("customers", "fleet_vehicles", "repair_orders", "inventory_items"):
        _positive(name, getattr(args, name))

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(Tenant).where(Tenant.slug == args.slug))
        if existing:
            print(
                f"Performance tenant already exists: slug={existing.slug} tenant_id={existing.id}. "
                "No data was changed."
            )
            return

        tenant = Tenant(
            id=uuid4(),
            name="Diesel Bridge Performance Lab",
            slug=args.slug,
            email="performance-lab@example.invalid",
            phone="555-010-9000",
            address="100 Synthetic Freight Way, Raleigh, NC 27601",
            is_active=True,
            enrollment_status="approved",
            labor_rate=Decimal("145.00"),
            internal_labor_rate=Decimal("65.00"),
            fleet_company_name="Performance Fleet",
            order_number_prefix="PERF",
        )
        db.add(tenant)
        await db.flush()

        owner = User(
            id=uuid4(),
            email=args.owner_email.lower(),
            hashed_password=get_password_hash(args.owner_password),
            first_name="Performance",
            last_name="Owner",
            role=UserRole.GARAGE_OWNER,
            tenant_id=tenant.id,
            is_active=True,
            is_verified=True,
        )
        mechanics = [
            User(
                id=uuid4(),
                email=f"performance-mechanic-{index}@example.invalid",
                hashed_password=get_password_hash(f"mechanic-{index}-{uuid4().hex}"),
                first_name="Performance",
                last_name=f"Mechanic {index}",
                role=UserRole.MECHANIC,
                tenant_id=tenant.id,
                is_active=True,
                is_verified=True,
            )
            for index in range(1, 6)
        ]
        db.add(owner)
        db.add_all(mechanics)
        await db.flush()
        tenant.owner_id = owner.id

        customers = [
            Customer(
                id=uuid4(),
                tenant_id=tenant.id,
                first_name=f"Driver{index}",
                last_name="Performance",
                company_name=f"Performance Carrier {index:03d}",
                email=f"performance-customer-{index}@example.invalid",
                phone=f"555-010-{index:04d}",
                billing_address_line1=f"{index} Fleet Road",
                billing_city="Raleigh",
                billing_state="NC",
                billing_zip="27601",
                fleet_enabled=index % 4 == 0,
                source="performance_seed",
            )
            for index in range(1, args.customers + 1)
        ]
        fleet_customer = Customer(
            id=uuid4(),
            tenant_id=tenant.id,
            first_name="Performance",
            last_name="Fleet",
            company_name="Performance Fleet",
            email="performance-fleet@example.invalid",
            phone="555-010-9999",
            is_internal_fleet=True,
            fleet_enabled=True,
            source="performance_seed",
        )
        db.add_all(customers + [fleet_customer])
        await db.flush()
        tenant.default_fleet_authority_customer_id = fleet_customer.id

        customer_vehicles = [
            Vehicle(
                id=uuid4(),
                tenant_id=tenant.id,
                customer_id=customer.id,
                vin=_vin(index),
                unit_number=f"C-{index:04d}",
                make="Freightliner" if index % 2 else "Peterbilt",
                model="Cascadia" if index % 2 else "579",
                year=2020 + index % 6,
                license_plate=f"PC{index:05d}",
                mileage=100_000 + index * 713,
                pm_interval_miles=25_000,
                next_pm_miles=130_000 + index * 713,
                source="performance_seed",
            )
            for index, customer in enumerate(customers, start=1)
        ]
        fleet_vehicles = [
            Vehicle(
                id=uuid4(),
                tenant_id=tenant.id,
                customer_id=fleet_customer.id,
                vin=_vin(10_000 + index),
                unit_number=f"F-{index:04d}",
                make="Volvo" if index % 2 else "Kenworth",
                model="VNL" if index % 2 else "T680",
                year=2020 + index % 6,
                license_plate=f"PF{index:05d}",
                mileage=250_000 + index * 911,
                driver_name=f"Fleet Driver {index}",
                driver_phone=f"555-011-{index:04d}",
                status_override="active" if index % 3 else "yard",
                pm_interval_miles=25_000,
                next_pm_miles=252_000 + index * 911,
                source="performance_seed",
            )
            for index in range(1, args.fleet_vehicles + 1)
        ]
        db.add_all(customer_vehicles + fleet_vehicles)

        inventory = [
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku=f"PERF-PART-{index:04d}",
                name=f"Performance replacement part {index:04d}",
                description="Synthetic inventory for isolated performance testing.",
                category=("Filters", "Brakes", "Fluids", "Electrical")[index % 4],
                stock_quantity=100 + index % 50,
                reorder_level=10,
                cost=Decimal("25.00") + Decimal(index % 40),
                selling_price=Decimal("55.00") + Decimal(index % 40),
                source="performance_seed",
            )
            for index in range(1, args.inventory_items + 1)
        ]
        db.add_all(inventory)
        await db.flush()

        all_vehicles = customer_vehicles + fleet_vehicles
        statuses = (
            [RepairOrderStatus.PAID] * 55
            + [RepairOrderStatus.COMPLETED] * 15
            + [RepairOrderStatus.INVOICED] * 10
            + [RepairOrderStatus.QUOTED] * 7
            + [RepairOrderStatus.IN_PROGRESS] * 7
            + [RepairOrderStatus.PENDING_REVIEW] * 4
            + [RepairOrderStatus.APPROVED] * 2
        )
        orders = []
        for index in range(1, args.repair_orders + 1):
            vehicle = all_vehicles[(index - 1) % len(all_vehicles)]
            is_internal = vehicle.customer_id == fleet_customer.id
            status = statuses[(index - 1) % len(statuses)]
            created_at = now - timedelta(hours=index * 3)
            orders.append(
                RepairOrder(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    customer_id=vehicle.customer_id,
                    vehicle_id=vehicle.id,
                    order_number=f"PERF-{index:07d}",
                    status=status,
                    description=f"Performance seed repair order {index}: diagnostics and service",
                    assigned_mechanic_id=mechanics[index % len(mechanics)].id if status not in {RepairOrderStatus.PAID, RepairOrderStatus.INVOICED} else None,
                    total_parts_cost=Decimal("180.00"),
                    total_labor_cost=Decimal("290.00"),
                    total_cost=Decimal("470.00"),
                    is_internal=is_internal,
                    is_fleet_work=is_internal,
                    created_at=created_at,
                )
            )
        db.add_all(orders)
        await db.flush()

        workspace_order = orders[0]
        workspace_parts_total = sum(
            (Decimal(str(part.selling_price)) for part in inventory[:12]),
            Decimal("0.00"),
        )
        workspace_labor_total = Decimal("145.00") * 6
        workspace_order.status = RepairOrderStatus.IN_PROGRESS
        workspace_order.description = "Performance workspace order with parts and labor lines"
        workspace_order.total_parts_cost = workspace_parts_total
        workspace_order.total_labor_cost = workspace_labor_total
        workspace_order.total_cost = workspace_parts_total + workspace_labor_total
        workspace_order.assigned_mechanic_id = mechanics[0].id

        db.add_all(
            [
                PartsUsage(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    repair_order_id=workspace_order.id,
                    inventory_id=part.id,
                    quantity=Decimal("1.00"),
                    unit_cost=part.cost,
                    unit_price=part.selling_price,
                    list_price=part.selling_price,
                    total_price=part.selling_price,
                )
                for part in inventory[:12]
            ]
            + [
                Labor(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    repair_order_id=workspace_order.id,
                    description=f"Performance workspace labor operation {index}",
                    hours=Decimal("1.00"),
                    hourly_rate=Decimal("145.00"),
                    total_cost=Decimal("145.00"),
                    line_type=LaborLineType.MANUAL,
                    mechanic_id=mechanics[index % len(mechanics)].id,
                )
                for index in range(1, 7)
            ]
        )
        await db.commit()

        print("Performance environment seeded successfully.")
        print(f"tenant_slug={tenant.slug}")
        print(f"owner_email={owner.email}")
        print(f"workspace_repair_order_id={workspace_order.id}")
        print(
            "counts="
            f"customers:{len(customers) + 1} vehicles:{len(all_vehicles)} "
            f"repair_orders:{len(orders)} inventory:{len(inventory)}"
        )


if __name__ == "__main__":
    asyncio.run(seed(_parse_args()))
