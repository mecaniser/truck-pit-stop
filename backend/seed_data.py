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
from app.db.models.service import ServiceCategory, Service
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
            first_name="Admin",
            last_name="User",
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
            first_name="Mike",
            last_name="Johnson",
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
            first_name="John",
            last_name="Trucker",
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
            first_name="Sarah",
            last_name="Hauler",
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

        # Create Service Categories
        cat_pm = ServiceCategory(
            id=uuid4(),
            tenant_id=tenant.id,
            name="PM Services",
            description="Preventive maintenance to keep your fleet running",
            icon="🔧",
            sort_order=1,
        )
        db.add(cat_pm)

        cat_brakes = ServiceCategory(
            id=uuid4(),
            tenant_id=tenant.id,
            name="Brakes",
            description="Brake services and repairs",
            icon="🛑",
            sort_order=2,
        )
        db.add(cat_brakes)

        cat_inspections = ServiceCategory(
            id=uuid4(),
            tenant_id=tenant.id,
            name="Inspections",
            description="Safety and compliance inspections",
            icon="📋",
            sort_order=3,
        )
        db.add(cat_inspections)

        cat_tires = ServiceCategory(
            id=uuid4(),
            tenant_id=tenant.id,
            name="Tires",
            description="Tire services and replacements",
            icon="🛞",
            sort_order=4,
        )
        db.add(cat_tires)

        cat_other = ServiceCategory(
            id=uuid4(),
            tenant_id=tenant.id,
            name="Other Services",
            description="Additional truck services",
            icon="🛠️",
            sort_order=5,
        )
        db.add(cat_other)
        await db.flush()

        # Create Services
        services = [
            # PM Services
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_pm.id,
                name="PM Service - Level A",
                description="Basic preventive maintenance: oil change, filter replacement, fluid check, and 23-point inspection.",
                duration_minutes=60,
                base_price=Decimal("249.00"),
                icon="🛢️",
                sort_order=1,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_pm.id,
                name="PM Service - Level B",
                description="Comprehensive PM: oil change, all filters, fluid top-off, greasing, and 50-point inspection.",
                duration_minutes=120,
                base_price=Decimal("449.00"),
                icon="⚙️",
                sort_order=2,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_pm.id,
                name="PM Service - Level C",
                description="Full service PM: includes Level B plus transmission service, coolant check, and brake adjustment.",
                duration_minutes=180,
                base_price=Decimal("699.00"),
                icon="🔩",
                sort_order=3,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_pm.id,
                name="Oil Change Only",
                description="Quick oil and filter change with synthetic diesel oil.",
                duration_minutes=45,
                base_price=Decimal("189.00"),
                icon="🛢️",
                sort_order=4,
            ),
            # Brakes
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_brakes.id,
                name="Brake Inspection",
                description="Complete brake system inspection with detailed condition report.",
                duration_minutes=30,
                base_price=Decimal("59.00"),
                icon="🔍",
                sort_order=1,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_brakes.id,
                name="Brake Pad Replacement - Per Axle",
                description="Replace brake pads on one axle. Includes inspection and adjustment.",
                duration_minutes=90,
                base_price=Decimal("349.00"),
                icon="🛑",
                sort_order=2,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_brakes.id,
                name="Full Brake Job - All Axles",
                description="Complete brake service: pads, drums/rotors inspection, adjustment on all axles.",
                duration_minutes=240,
                base_price=Decimal("1299.00"),
                icon="🔴",
                sort_order=3,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_brakes.id,
                name="Brake Adjustment",
                description="Adjust and set brake slack adjusters for optimal performance.",
                duration_minutes=45,
                base_price=Decimal("89.00"),
                icon="🔧",
                sort_order=4,
            ),
            # Inspections
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_inspections.id,
                name="DOT Annual Inspection",
                description="Complete DOT annual inspection and certification. Required for compliance.",
                duration_minutes=90,
                base_price=Decimal("149.00"),
                icon="✅",
                sort_order=1,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_inspections.id,
                name="Monthly Safety Inspection",
                description="Comprehensive monthly inspection covering all major systems and safety equipment.",
                duration_minutes=60,
                base_price=Decimal("99.00"),
                icon="📅",
                sort_order=2,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_inspections.id,
                name="Weekly Safety Check",
                description="Quick weekly safety inspection: lights, tires, brakes, fluids, and walk-around.",
                duration_minutes=30,
                base_price=Decimal("49.00"),
                icon="📋",
                sort_order=3,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_inspections.id,
                name="Pre-Trip Inspection",
                description="Detailed pre-trip inspection before long hauls. Peace of mind on the road.",
                duration_minutes=45,
                base_price=Decimal("79.00"),
                icon="🚛",
                sort_order=4,
            ),
            # Tires
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_tires.id,
                name="Tire Change - Single",
                description="Mount and balance one new tire. Disposal of old tire included.",
                duration_minutes=30,
                base_price=Decimal("45.00"),
                icon="🛞",
                sort_order=1,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_tires.id,
                name="Tire Change - Per Axle",
                description="Mount and balance tires on one axle (2 or 4 tires). Disposal included.",
                duration_minutes=60,
                base_price=Decimal("120.00"),
                icon="🔄",
                sort_order=2,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_tires.id,
                name="Tire Rotation",
                description="Rotate tires for even wear and extended life.",
                duration_minutes=45,
                base_price=Decimal("79.00"),
                icon="🔃",
                sort_order=3,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_tires.id,
                name="Tire Repair - Patch/Plug",
                description="Professional tire repair. Assessment to determine if repair is safe.",
                duration_minutes=30,
                base_price=Decimal("35.00"),
                icon="🔧",
                sort_order=4,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_tires.id,
                name="Wheel Alignment",
                description="Full wheel alignment check and adjustment for all axles.",
                duration_minutes=90,
                base_price=Decimal("249.00"),
                icon="📐",
                sort_order=5,
            ),
            # Other Services
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_other.id,
                name="Diagnostic Scan",
                description="Computer diagnostic for check engine lights, fault codes, and system analysis.",
                duration_minutes=30,
                base_price=Decimal("99.00"),
                icon="💻",
                sort_order=1,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_other.id,
                name="A/C Service",
                description="A/C system inspection, leak check, and refrigerant recharge.",
                duration_minutes=60,
                base_price=Decimal("179.00"),
                icon="❄️",
                sort_order=2,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_other.id,
                name="Battery Test & Replacement",
                description="Load test batteries and replace if needed. Includes terminal cleaning.",
                duration_minutes=30,
                base_price=Decimal("49.00"),
                icon="🔋",
                sort_order=3,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_other.id,
                name="DEF System Service",
                description="DEF system inspection, fluid top-off, and filter replacement.",
                duration_minutes=45,
                base_price=Decimal("129.00"),
                icon="💧",
                sort_order=4,
            ),
            Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat_other.id,
                name="DPF Cleaning",
                description="Diesel Particulate Filter cleaning and regeneration service.",
                duration_minutes=120,
                base_price=Decimal("399.00"),
                icon="🌫️",
                sort_order=5,
            ),
        ]
        
        for svc in services:
            db.add(svc)

        await db.commit()
        print("✅ Database seeded successfully!")
        print(f"\n📦 {len(inventory_items)} inventory items created")
        print(f"🔧 {len(services)} services created in 5 categories")
        print("\nTest accounts created:")
        print("  Admin: admin@truckpitstop.com / admin123")
        print("  Mechanic: mike@truckpitstop.com / mechanic123")
        print("  Customer 1: john.trucker@email.com / customer123")
        print("  Customer 2: sarah.hauler@email.com / customer123")


if __name__ == "__main__":
    asyncio.run(seed())

