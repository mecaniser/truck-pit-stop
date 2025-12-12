"""
Seed script to populate the database with test data.
Run with: python seed_data.py
"""
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta
from app.db.session import AsyncSessionLocal
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.inventory import Inventory
from app.core.security import get_password_hash


async def seed():
    async with AsyncSessionLocal() as db:
        # Check if data already exists
        from sqlalchemy import select
        result = await db.execute(select(Tenant))
        if result.scalar_one_or_none():
            print("Database already seeded. Skipping...")
            return

        print("Seeding database...")

        # Create Tenant (Garage)
        tenant = Tenant(
            id=uuid4(),
            name="Truck Pit Stop Wisconsin",
            slug="truck-pit-stop-wi",
            address="123 Highway 41, Milwaukee, WI 53202",
            phone="(414) 555-0123",
            email="service@truckpitstopwi.com",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        # Create Admin User
        admin_user = User(
            id=uuid4(),
            email="admin@truckpitstop.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin User",
            phone="(414) 555-0001",
            role=UserRole.GARAGE_ADMIN,
            tenant_id=tenant.id,
            is_active=True,
            is_verified=True,
        )
        db.add(admin_user)

        # Create Mechanic
        mechanic = User(
            id=uuid4(),
            email="mike@truckpitstop.com",
            hashed_password=get_password_hash("mechanic123"),
            full_name="Mike Johnson",
            phone="(414) 555-0002",
            role=UserRole.MECHANIC,
            tenant_id=tenant.id,
            is_active=True,
            is_verified=True,
        )
        db.add(mechanic)

        # Create Customers
        customer1 = Customer(
            id=uuid4(),
            tenant_id=tenant.id,
            first_name="John",
            last_name="Trucker",
            email="john.trucker@email.com",
            phone="(414) 555-1001",
            billing_address_line1="456 Freight Lane",
            billing_city="Milwaukee",
            billing_state="WI",
            billing_zip="53203",
        )
        db.add(customer1)

        customer2 = Customer(
            id=uuid4(),
            tenant_id=tenant.id,
            first_name="Sarah",
            last_name="Hauler",
            email="sarah.hauler@email.com",
            phone="(414) 555-1002",
            billing_address_line1="789 Diesel Drive",
            billing_city="Waukesha",
            billing_state="WI",
            billing_zip="53186",
        )
        db.add(customer2)
        await db.flush()

        # Create Customer User accounts
        customer1_user = User(
            id=uuid4(),
            email="john.trucker@email.com",
            hashed_password=get_password_hash("customer123"),
            full_name="John Trucker",
            phone="(414) 555-1001",
            role=UserRole.CUSTOMER,
            tenant_id=tenant.id,
            customer_id=customer1.id,
            is_active=True,
            is_verified=True,
        )
        db.add(customer1_user)

        customer2_user = User(
            id=uuid4(),
            email="sarah.hauler@email.com",
            hashed_password=get_password_hash("customer123"),
            full_name="Sarah Hauler",
            phone="(414) 555-1002",
            role=UserRole.CUSTOMER,
            tenant_id=tenant.id,
            customer_id=customer2.id,
            is_active=True,
            is_verified=True,
        )
        db.add(customer2_user)

        # Create Vehicles for Customer 1
        vehicle1 = Vehicle(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vin="1HTMMAAM45H123456",
            make="Peterbilt",
            model="579",
            year=2022,
            license_plate="WI-TRUCK1",
            color="Red",
            mileage=145000,
        )
        db.add(vehicle1)

        vehicle2 = Vehicle(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vin="3AKJHHDR8LSLA7890",
            make="Freightliner",
            model="Cascadia",
            year=2020,
            license_plate="WI-TRUCK2",
            color="White",
            mileage=230000,
        )
        db.add(vehicle2)

        # Create Vehicles for Customer 2
        vehicle3 = Vehicle(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer2.id,
            vin="1XKAD49X35J654321",
            make="Kenworth",
            model="T680",
            year=2021,
            license_plate="WI-HAUL01",
            color="Blue",
            mileage=175000,
        )
        db.add(vehicle3)
        await db.flush()

        # Create Repair Orders - In Progress
        repair1 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vehicle_id=vehicle1.id,
            order_number="RO-2024-001",
            status=RepairOrderStatus.IN_PROGRESS,
            description="Engine oil leak repair and full service",
            customer_notes="Noticed oil spots under the truck after parking",
            internal_notes="Suspected rear main seal leak",
            assigned_mechanic_id=mechanic.id,
            total_parts_cost=Decimal("450.00"),
            total_labor_cost=Decimal("600.00"),
            total_cost=Decimal("1050.00"),
        )
        db.add(repair1)

        repair2 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer2.id,
            vehicle_id=vehicle3.id,
            order_number="RO-2024-002",
            status=RepairOrderStatus.IN_PROGRESS,
            description="Brake system overhaul - all axles",
            customer_notes="Brakes feel spongy, need inspection before long haul",
            assigned_mechanic_id=mechanic.id,
            total_parts_cost=Decimal("1200.00"),
            total_labor_cost=Decimal("800.00"),
            total_cost=Decimal("2000.00"),
        )
        db.add(repair2)

        # Create Repair Orders - Completed/Paid (History)
        repair3 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vehicle_id=vehicle1.id,
            order_number="RO-2023-045",
            status=RepairOrderStatus.PAID,
            description="Annual DOT inspection and preventive maintenance",
            total_parts_cost=Decimal("320.00"),
            total_labor_cost=Decimal("400.00"),
            total_cost=Decimal("720.00"),
        )
        # Backdate this repair
        repair3.created_at = datetime.utcnow() - timedelta(days=90)
        db.add(repair3)

        repair4 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vehicle_id=vehicle2.id,
            order_number="RO-2023-032",
            status=RepairOrderStatus.PAID,
            description="Transmission fluid change and clutch adjustment",
            total_parts_cost=Decimal("180.00"),
            total_labor_cost=Decimal("350.00"),
            total_cost=Decimal("530.00"),
        )
        repair4.created_at = datetime.utcnow() - timedelta(days=120)
        db.add(repair4)

        repair5 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vehicle_id=vehicle1.id,
            order_number="RO-2023-018",
            status=RepairOrderStatus.PAID,
            description="Turbo replacement and EGR cleaning",
            total_parts_cost=Decimal("2800.00"),
            total_labor_cost=Decimal("1200.00"),
            total_cost=Decimal("4000.00"),
        )
        repair5.created_at = datetime.utcnow() - timedelta(days=180)
        db.add(repair5)

        repair6 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer2.id,
            vehicle_id=vehicle3.id,
            order_number="RO-2023-041",
            status=RepairOrderStatus.PAID,
            description="A/C system repair and recharge",
            total_parts_cost=Decimal("450.00"),
            total_labor_cost=Decimal("300.00"),
            total_cost=Decimal("750.00"),
        )
        repair6.created_at = datetime.utcnow() - timedelta(days=60)
        db.add(repair6)

        # Create a Quoted repair waiting for approval
        repair7 = RepairOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer1.id,
            vehicle_id=vehicle2.id,
            order_number="RO-2024-003",
            status=RepairOrderStatus.QUOTED,
            description="DPF filter replacement and regen service",
            customer_notes="Check engine light on, reduced power mode",
            total_parts_cost=Decimal("3500.00"),
            total_labor_cost=Decimal("600.00"),
            total_cost=Decimal("4100.00"),
        )
        db.add(repair7)

        # Create Inventory Items
        inventory_items = [
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="BRK-PAD-001",
                name="Heavy Duty Brake Pads - Front",
                description="Premium ceramic brake pads for semi-trucks",
                category="Brakes",
                stock_quantity=24,
                reorder_level=10,
                cost=Decimal("85.00"),
                selling_price=Decimal("145.00"),
                supplier_name="FleetParts Pro",
                supplier_contact="1-800-555-0101",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="BRK-PAD-002",
                name="Heavy Duty Brake Pads - Rear",
                description="Premium ceramic brake pads for semi-trucks",
                category="Brakes",
                stock_quantity=18,
                reorder_level=10,
                cost=Decimal("95.00"),
                selling_price=Decimal("165.00"),
                supplier_name="FleetParts Pro",
                supplier_contact="1-800-555-0101",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="BRK-ROTOR-001",
                name="Brake Rotor - 15 inch",
                description="Heavy duty vented brake rotor",
                category="Brakes",
                stock_quantity=8,
                reorder_level=4,
                cost=Decimal("220.00"),
                selling_price=Decimal("350.00"),
                supplier_name="FleetParts Pro",
                supplier_contact="1-800-555-0101",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="OIL-15W40-5G",
                name="Diesel Engine Oil 15W-40 (5 Gal)",
                description="Full synthetic diesel engine oil",
                category="Fluids",
                stock_quantity=12,
                reorder_level=5,
                cost=Decimal("75.00"),
                selling_price=Decimal("120.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="OIL-FLT-001",
                name="Oil Filter - Cummins ISX",
                description="OEM spec oil filter for Cummins ISX engines",
                category="Filters",
                stock_quantity=35,
                reorder_level=15,
                cost=Decimal("18.00"),
                selling_price=Decimal("35.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="AIR-FLT-001",
                name="Air Filter - Primary",
                description="Heavy duty primary air filter",
                category="Filters",
                stock_quantity=20,
                reorder_level=8,
                cost=Decimal("45.00"),
                selling_price=Decimal("85.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="AIR-FLT-002",
                name="Air Filter - Secondary",
                description="Heavy duty secondary/safety air filter",
                category="Filters",
                stock_quantity=15,
                reorder_level=8,
                cost=Decimal("25.00"),
                selling_price=Decimal("55.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="FUEL-FLT-001",
                name="Fuel Filter Kit",
                description="Primary and secondary fuel filter set",
                category="Filters",
                stock_quantity=3,
                reorder_level=6,
                cost=Decimal("65.00"),
                selling_price=Decimal("110.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="BELT-SERP-001",
                name="Serpentine Belt - 10 Rib",
                description="Heavy duty serpentine belt",
                category="Belts & Hoses",
                stock_quantity=6,
                reorder_level=4,
                cost=Decimal("55.00"),
                selling_price=Decimal("95.00"),
                supplier_name="FleetParts Pro",
                supplier_contact="1-800-555-0101",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="COOL-ANT-5G",
                name="Extended Life Coolant (5 Gal)",
                description="Heavy duty extended life antifreeze/coolant",
                category="Fluids",
                stock_quantity=8,
                reorder_level=4,
                cost=Decimal("45.00"),
                selling_price=Decimal("75.00"),
                supplier_name="TruckLube Supply",
                supplier_contact="1-800-555-0202",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="TURBO-ACT-001",
                name="Turbo Actuator",
                description="Variable geometry turbo actuator",
                category="Engine",
                stock_quantity=2,
                reorder_level=2,
                cost=Decimal("450.00"),
                selling_price=Decimal("750.00"),
                supplier_name="Diesel Parts Direct",
                supplier_contact="1-800-555-0303",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="DPF-FLTR-001",
                name="DPF Filter Assembly",
                description="Diesel particulate filter - remanufactured",
                category="Exhaust",
                stock_quantity=1,
                reorder_level=1,
                cost=Decimal("1800.00"),
                selling_price=Decimal("2800.00"),
                supplier_name="Diesel Parts Direct",
                supplier_contact="1-800-555-0303",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="BATT-HD-001",
                name="Heavy Duty Battery - Group 31",
                description="1000 CCA commercial truck battery",
                category="Electrical",
                stock_quantity=4,
                reorder_level=2,
                cost=Decimal("180.00"),
                selling_price=Decimal("280.00"),
                supplier_name="Battery Warehouse",
                supplier_contact="1-800-555-0404",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="STRTR-001",
                name="Starter Motor - Delco 39MT",
                description="Remanufactured heavy duty starter",
                category="Electrical",
                stock_quantity=0,
                reorder_level=1,
                cost=Decimal("350.00"),
                selling_price=Decimal("550.00"),
                supplier_name="Diesel Parts Direct",
                supplier_contact="1-800-555-0303",
            ),
            Inventory(
                id=uuid4(),
                tenant_id=tenant.id,
                sku="ALT-001",
                name="Alternator - 160 Amp",
                description="Heavy duty alternator for commercial trucks",
                category="Electrical",
                stock_quantity=2,
                reorder_level=1,
                cost=Decimal("280.00"),
                selling_price=Decimal("450.00"),
                supplier_name="Diesel Parts Direct",
                supplier_contact="1-800-555-0303",
            ),
        ]
        
        for item in inventory_items:
            db.add(item)

        await db.commit()
        print("✅ Database seeded successfully!")
        print(f"\n📦 {len(inventory_items)} inventory items created")
        print("\nTest accounts created:")
        print("  Admin: admin@truckpitstop.com / admin123")
        print("  Mechanic: mike@truckpitstop.com / mechanic123")
        print("  Customer 1: john.trucker@email.com / customer123")
        print("  Customer 2: sarah.hauler@email.com / customer123")


if __name__ == "__main__":
    asyncio.run(seed())

