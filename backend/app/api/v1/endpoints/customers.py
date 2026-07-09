import re
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, asc, desc, literal_column
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.phone import normalize_phone
from app.core.logging import get_logger
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.contact import Contact
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder
from app.db.models.inventory import PartsUsage
from app.db.models.labor import Labor
from app.db.models.appointment import Appointment
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage
from app.db.models.user_customer_link import UserCustomerLink
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerWithVehiclesResponse,
    CustomerMergeRequest,
    CustomerMergeResult,
)
from app.schemas.vehicle import VehicleBase, VehicleUpdate, VehicleResponse
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse
from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot
from app.services.vin_decoder_service import decode_vin, VINDecodeResult

router = APIRouter()
logger = get_logger(__name__)


def require_role(*allowed_roles: UserRole):
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


async def get_customer_balances(db: AsyncSession, customer_ids: list) -> dict:
    """Outstanding AR per customer: sum(invoice.total_amount) - sum(payments.amount),
    across all of a customer's invoices. Two aggregate queries (not N+1) so this
    scales to the full customer list, not just a single detail view."""
    if not customer_ids:
        return {}

    invoiced_result = await db.execute(
        select(RepairOrder.customer_id, func.coalesce(func.sum(Invoice.total_amount), 0))
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .where(RepairOrder.customer_id.in_(customer_ids))
        .group_by(RepairOrder.customer_id)
    )
    invoiced_by_customer = dict(invoiced_result.all())

    paid_result = await db.execute(
        select(RepairOrder.customer_id, func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .where(RepairOrder.customer_id.in_(customer_ids))
        .group_by(RepairOrder.customer_id)
    )
    paid_by_customer = dict(paid_result.all())

    return {
        cid: invoiced_by_customer.get(cid, 0) - paid_by_customer.get(cid, 0)
        for cid in customer_ids
    }


async def get_customer_vehicle_info(db: AsyncSession, customer_ids: list) -> dict:
    """Vehicle count + (single) license plate per customer. Plate is only
    returned when a customer has exactly one vehicle — with several vehicles
    there's no single plate to show, so the UI falls back to showing the count."""
    if not customer_ids:
        return {}

    count_result = await db.execute(
        select(Vehicle.customer_id, func.count(Vehicle.id))
        .where(Vehicle.customer_id.in_(customer_ids))
        .group_by(Vehicle.customer_id)
    )
    counts = dict(count_result.all())

    single_vehicle_ids = [cid for cid, count in counts.items() if count == 1]
    plates_by_customer = {}
    if single_vehicle_ids:
        plate_result = await db.execute(
            select(Vehicle.customer_id, Vehicle.license_plate)
            .where(Vehicle.customer_id.in_(single_vehicle_ids))
        )
        plates_by_customer = dict(plate_result.all())

    return {
        cid: {"count": counts.get(cid, 0), "plate": plates_by_customer.get(cid)}
        for cid in customer_ids
    }


def _customer_response_with_balance(
    customer: Customer,
    balances: dict,
    vehicle_info: Optional[dict] = None,
    search: Optional[str] = None,
) -> CustomerResponse:
    response = CustomerResponse.model_validate(customer)
    response.balance = balances.get(customer.id, 0)
    if vehicle_info:
        info = vehicle_info.get(customer.id, {})
        response.vehicle_count = info.get("count", 0)
        response.single_vehicle_license_plate = info.get("plate")
    if search:
        response.matched_fields = _customer_matched_fields(customer, search)
    return response


@router.post("", response_model=CustomerWithVehiclesResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    # Require either a vehicle or explicit no_vehicle flag
    if not customer_data.initial_vehicle and not customer_data.no_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer must have a vehicle or 'no_vehicle' must be set to true",
        )
    
    # Check if customer email already exists for this tenant
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.email == customer_data.email,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer with this email already exists",
        )
    
    # Extract customer fields only (exclude vehicle data)
    customer_fields = customer_data.model_dump(exclude={'initial_vehicle', 'no_vehicle'})
    customer_fields["phone"] = normalize_phone(customer_fields.get("phone"))
    if "company_name" in customer_fields:
        company = (customer_fields.get("company_name") or "").strip()
        customer_fields["company_name"] = company or None
    customer = Customer(
        tenant_id=current_user.tenant_id,
        **customer_fields,
    )
    
    db.add(customer)
    await db.flush()  # Get customer.id before creating vehicle
    
    # Create initial vehicle if provided
    if customer_data.initial_vehicle:
        vehicle = Vehicle(
            tenant_id=current_user.tenant_id,
            customer_id=customer.id,
            **customer_data.initial_vehicle.model_dump(),
        )
        await sync_vehicle_nhtsa_snapshot(vehicle)
        db.add(vehicle)
    
    await db.commit()
    
    # Reload with vehicles
    result = await db.execute(
        select(Customer)
        .options(selectinload(Customer.vehicles))
        .where(Customer.id == customer.id)
    )
    customer = result.scalar_one()
    
    return CustomerWithVehiclesResponse.model_validate(customer)


# Fields the customer list may be sorted by. Anything else falls back to name.
CUSTOMER_SORT_FIELDS = {"name", "balance", "vehicle_count"}


def _customer_search_filter(search: Optional[str]):
    """OR-match across name / company / email / DOT / MC (ILIKE substring)
    plus a phone match when the term itself looks like a phone number.

    Phone matching only kicks in when the search term, after stripping common
    phone punctuation (spaces/dashes/parens/dots/plus), is made up entirely of
    digits — e.g. "704-705" or "(704) 705-0486". A term with real letters in
    it (e.g. "77 cargo") is clearly a name/company search, not a phone
    number, and matching its incidental digits ("77") as a phone substring
    would match nearly every phone on file and swamp the results.
    """
    term = (search or "").strip()
    if not term:
        return None
    like = f"%{term}%"
    clauses = [
        Customer.first_name.ilike(like),
        Customer.last_name.ilike(like),
        (Customer.first_name + literal_column("' '") + Customer.last_name).ilike(like),
        Customer.company_name.ilike(like),
        Customer.email.ilike(like),
        Customer.usdot_number.ilike(like),
        Customer.mc_number.ilike(like),
    ]
    stripped = re.sub(r"[\s().+-]", "", term)
    if stripped and stripped.isdigit():
        clauses.append(
            func.regexp_replace(func.coalesce(Customer.phone, ""), r"\D", "", "g").ilike(f"%{stripped}%")
        )
    return or_(*clauses)


def _customer_matched_fields(customer: Customer, search: Optional[str]) -> List[str]:
    """Which field(s) on this customer actually satisfied the search term —
    mirrors _customer_search_filter's own logic exactly (same digit-stripping
    rule for phone) so the two can't drift out of sync. Used to show the
    user *why* a result matched (e.g. a "Phone" or "VIN" badge)."""
    term = (search or "").strip()
    if not term:
        return []
    q = term.lower()
    matched: List[str] = []

    def has(value: Optional[str]) -> bool:
        return bool(value) and q in value.lower()

    if has(customer.first_name) or has(customer.last_name) or has(f"{customer.first_name or ''} {customer.last_name or ''}"):
        matched.append("name")
    if has(customer.company_name):
        matched.append("company")
    if has(customer.email):
        matched.append("email")
    if has(customer.usdot_number):
        matched.append("usdot")
    if has(customer.mc_number):
        matched.append("mc")
    stripped = re.sub(r"[\s().+-]", "", term)
    if stripped and stripped.isdigit():
        phone_digits = re.sub(r"\D", "", customer.phone or "")
        if stripped in phone_digits:
            matched.append("phone")
    return matched


def _vehicle_count_subquery():
    return (
        select(func.count(Vehicle.id))
        .where(Vehicle.customer_id == Customer.id)
        .correlate(Customer)
        .scalar_subquery()
    )


def _balance_subquery():
    """Outstanding AR as a scalar subquery, for ORDER BY balance.
    invoiced - paid across the customer's repair orders."""
    invoiced = (
        select(func.coalesce(func.sum(Invoice.total_amount), 0))
        .select_from(RepairOrder)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .where(RepairOrder.customer_id == Customer.id)
        .correlate(Customer)
        .scalar_subquery()
    )
    paid = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .select_from(RepairOrder)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .where(RepairOrder.customer_id == Customer.id)
        .correlate(Customer)
        .scalar_subquery()
    )
    return invoiced - paid


def _customer_order_by(sort: Optional[str], order: str):
    """Return the ORDER BY expression list for the customer list."""
    direction = desc if order == "desc" else asc
    field = sort if sort in CUSTOMER_SORT_FIELDS else "name"
    if field == "balance":
        return [direction(_balance_subquery()), asc(Customer.id)]
    if field == "vehicle_count":
        return [direction(_vehicle_count_subquery()), asc(Customer.id)]
    # name: case-insensitive on first then last, with id as a stable tiebreaker.
    return [
        direction(func.lower(Customer.first_name)),
        direction(func.lower(Customer.last_name)),
        asc(Customer.id),
    ]


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    search: Optional[str] = Query(None, description="Filter by name, company, email, or phone"),
    sort: Optional[str] = Query(None, description="name | balance | vehicle_count"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own profile
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        result = await db.execute(
            select(Customer).where(Customer.id == current_user.customer_id)
        )
        customer = result.scalar_one_or_none()
        cust_ids = [customer.id] if customer else []
        balances = await get_customer_balances(db, cust_ids)
        vehicle_info = await get_customer_vehicle_info(db, cust_ids)
        customers = [_customer_response_with_balance(customer, balances, vehicle_info)] if customer else []
        total = len(customers)
        response_items = customers[skip : skip + limit] if paginated else customers
        return paginated_or_list(response_items, total, skip, limit, paginated)

    # Staff can see all customers in their tenant
    if not current_user.tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)

    # The internal-fleet house account is managed via the dedicated fleet view,
    # not listed among real customers.
    base_filter = and_(
        Customer.tenant_id == current_user.tenant_id,
        Customer.is_internal_fleet.is_(False),
    )
    search_filter = _customer_search_filter(search)
    where_clause = base_filter if search_filter is None else and_(base_filter, search_filter)

    # total reflects the *filtered* set so the UI count stays correct while searching.
    total_result = await db.execute(
        select(func.count(Customer.id)).where(where_clause)
    )
    total = total_result.scalar() or 0
    result = await db.execute(
        select(Customer)
        .where(where_clause)
        .order_by(*_customer_order_by(sort, order))
        .offset(skip)
        .limit(limit)
    )
    customers = result.scalars().all()
    cust_ids = [c.id for c in customers]
    balances = await get_customer_balances(db, cust_ids)
    vehicle_info = await get_customer_vehicle_info(db, cust_ids)
    items = [_customer_response_with_balance(c, balances, vehicle_info, search) for c in customers]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/internal-fleet", response_model=CustomerResponse)
async def get_internal_fleet_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    """Return the tenant's internal-fleet house account (the garage's own trucks)."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    from app.services.internal_fleet import ensure_internal_fleet_customer
    customer = await ensure_internal_fleet_customer(db, current_user.tenant_id)
    await db.commit()
    return CustomerResponse.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access: customers can only see their own profile
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    # Staff can only see customers in their tenant
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    balances = await get_customer_balances(db, [customer.id])
    vehicle_info = await get_customer_vehicle_info(db, [customer.id])
    return _customer_response_with_balance(customer, balances, vehicle_info)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    if "phone" in update_data:
        update_data["phone"] = normalize_phone(update_data["phone"])
    if "company_name" in update_data:
        company = (update_data.get("company_name") or "").strip()
        update_data["company_name"] = company or None
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    await db.commit()
    await db.refresh(customer)

    balances = await get_customer_balances(db, [customer.id])
    vehicle_info = await get_customer_vehicle_info(db, [customer.id])
    return _customer_response_with_balance(customer, balances, vehicle_info)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    if current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    repair_order_count_result = await db.execute(
        select(func.count(RepairOrder.id)).where(RepairOrder.customer_id == customer_id)
    )
    repair_order_count = repair_order_count_result.scalar() or 0
    if repair_order_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete customer with repair orders",
        )

    # If there is a linked customer-portal user, detach it from this customer.
    # For customer-role users, also deactivate access after detaching.
    linked_users_result = await db.execute(
        select(User).where(User.customer_id == customer_id)
    )
    linked_users = linked_users_result.scalars().all()
    for linked_user in linked_users:
        linked_user.customer_id = None
        if linked_user.role == UserRole.CUSTOMER:
            linked_user.is_active = False

    # Remove orphanable appointments so customer deletion can proceed cleanly.
    # Repair-order-backed history is still protected by the guard above.
    appointments_result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.customer_id == customer_id,
                Appointment.tenant_id == customer.tenant_id,
            )
        )
    )
    appointments = appointments_result.scalars().all()
    for appointment in appointments:
        await db.delete(appointment)

    # Delete vehicles explicitly so this endpoint does not rely on ORM cascade behavior.
    vehicles_result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.customer_id == customer_id,
                Vehicle.tenant_id == customer.tenant_id,
            )
        )
    )
    vehicles = vehicles_result.scalars().all()
    for vehicle in vehicles:
        await db.delete(vehicle)

    try:
        await db.delete(customer)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete customer due to related records",
        )

    return None


@router.post("/merge", response_model=CustomerMergeResult)
async def merge_customers(
    merge_request: CustomerMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
    )),
):
    """Merge two customer records that represent the same real company (e.g.
    one has an email but no phone, another has a phone but no email — a
    common gap from data imports). All of the loser's vehicles, repair
    orders (which carry their labor/parts/invoices/payments along via FK),
    contacts, appointments, and SMS history move to the winner. The loser is
    then deleted. This is destructive and cannot be undone — callers should
    show a diff/confirmation before calling this.
    """
    if merge_request.winner_id == merge_request.loser_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="winner_id and loser_id must be different customers",
        )

    winner_result = await db.execute(select(Customer).where(Customer.id == merge_request.winner_id))
    winner = winner_result.scalar_one_or_none()
    loser_result = await db.execute(select(Customer).where(Customer.id == merge_request.loser_id))
    loser = loser_result.scalar_one_or_none()

    if not winner or not loser:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if winner.tenant_id != current_user.tenant_id or loser.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if winner.tenant_id != loser.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge customers from different tenants",
        )

    # Vehicles
    vehicles_result = await db.execute(select(Vehicle).where(Vehicle.customer_id == loser.id))
    vehicles = vehicles_result.scalars().all()
    for v in vehicles:
        v.customer_id = winner.id
    vehicles_moved = len(vehicles)

    # Repair orders — carries labor, parts_usage, invoices, payments along
    # automatically since those key off repair_order_id, not customer_id.
    ros_result = await db.execute(select(RepairOrder).where(RepairOrder.customer_id == loser.id))
    repair_orders = ros_result.scalars().all()
    for ro in repair_orders:
        ro.customer_id = winner.id
    repair_orders_moved = len(repair_orders)

    # Contacts — reassign, then make sure at most one is_primary survives.
    contacts_result = await db.execute(select(Contact).where(Contact.customer_id == loser.id))
    contacts = contacts_result.scalars().all()
    for c in contacts:
        c.customer_id = winner.id
    contacts_moved = len(contacts)
    if contacts_moved:
        await _clear_other_primary_contacts(db, winner.id)

    # Appointments
    appts_result = await db.execute(select(Appointment).where(Appointment.customer_id == loser.id))
    appointments = appts_result.scalars().all()
    for a in appointments:
        a.customer_id = winner.id
    appointments_moved = len(appointments)

    # SMS message history
    sms_result = await db.execute(select(SMSMessage).where(SMSMessage.customer_id == loser.id))
    sms_messages = sms_result.scalars().all()
    for m in sms_messages:
        m.customer_id = winner.id
    sms_messages_moved = len(sms_messages)

    # Message thread: unique on (tenant_id, customer_id), so only one can
    # exist per customer. If only the loser has one, move it. If both have
    # one, keep the winner's and drop the loser's (no customer portal exists
    # yet, so there's no live conversation at risk today).
    winner_thread_result = await db.execute(
        select(MessageThread).where(MessageThread.customer_id == winner.id)
    )
    winner_thread = winner_thread_result.scalar_one_or_none()
    loser_thread_result = await db.execute(
        select(MessageThread).where(MessageThread.customer_id == loser.id)
    )
    loser_thread = loser_thread_result.scalar_one_or_none()

    if loser_thread and not winner_thread:
        loser_thread.customer_id = winner.id
        message_thread_action = "moved"
    elif loser_thread and winner_thread:
        await db.delete(loser_thread)
        message_thread_action = "kept_winner_deleted_loser"
    else:
        message_thread_action = "none"

    # Portal user link: User.customer_id is unique, so only one user can be
    # linked per customer. Same policy as message threads.
    winner_user_result = await db.execute(select(User).where(User.customer_id == winner.id))
    winner_user = winner_user_result.scalar_one_or_none()
    loser_user_result = await db.execute(select(User).where(User.customer_id == loser.id))
    loser_user = loser_user_result.scalar_one_or_none()

    if loser_user and not winner_user:
        loser_user.customer_id = winner.id
        user_link_action = "moved"
    elif loser_user and winner_user:
        loser_user.customer_id = None
        if loser_user.role == UserRole.CUSTOMER:
            loser_user.is_active = False
        user_link_action = "kept_winner_deleted_loser"
    else:
        user_link_action = "none"

    # UserCustomerLink rows for the loser must move or be dropped before the
    # loser can be deleted (FK), same unique-per-tenant reasoning as above.
    loser_links_result = await db.execute(
        select(UserCustomerLink).where(UserCustomerLink.customer_id == loser.id)
    )
    for link in loser_links_result.scalars().all():
        existing = await db.execute(
            select(UserCustomerLink).where(
                and_(
                    UserCustomerLink.user_id == link.user_id,
                    UserCustomerLink.tenant_id == link.tenant_id,
                    UserCustomerLink.customer_id == winner.id,
                )
            )
        )
        if existing.scalar_one_or_none():
            await db.delete(link)
        else:
            link.customer_id = winner.id

    winner_id_for_log = str(winner.id)
    loser_id_for_log = str(loser.id)
    try:
        # Flush the customer_id reassignments above before deleting `loser`.
        # Without this, SQLAlchemy's unit-of-work still sees the (now stale)
        # in-memory collections on `loser` (vehicles/repair_orders/contacts/etc,
        # loaded via their own `select(...).where(customer_id == loser.id)`
        # queries above) as belonging to it, and cascades accordingly on
        # delete — nulling or deleting rows we already just moved to `winner`.
        # Expiring `loser` forces a fresh reload of its relationships, which
        # will correctly come back empty now that the FK flush has landed.
        await db.flush()
        db.expire(loser)
        await db.delete(loser)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.error(
            "customer_merge_integrity_error",
            winner_id=winner_id_for_log,
            loser_id=loser_id_for_log,
            error=str(exc.orig) if exc.orig else str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Merge failed due to related records that could not be reassigned",
        )

    return CustomerMergeResult(
        winner_id=winner.id,
        loser_id=loser.id,
        vehicles_moved=vehicles_moved,
        repair_orders_moved=repair_orders_moved,
        contacts_moved=contacts_moved,
        appointments_moved=appointments_moved,
        sms_messages_moved=sms_messages_moved,
        message_thread_action=message_thread_action,
        user_link_action=user_link_action,
    )


# ============================================================================
# NESTED VEHICLE ENDPOINTS
# ============================================================================

@router.get("/{customer_id}/vehicles", response_model=List[VehicleResponse])
async def list_customer_vehicles(
    customer_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all vehicles for a specific customer"""
    # First verify customer exists and user has access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Get vehicles
    total_result = await db.execute(select(func.count(Vehicle.id)).where(Vehicle.customer_id == customer_id))
    total = total_result.scalar() or 0
    query = (
        select(Vehicle)
        .where(Vehicle.customer_id == customer_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    vehicles = result.scalars().all()
    items = [VehicleResponse.model_validate(v) for v in vehicles]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.post("/{customer_id}/vehicles", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_vehicle(
    customer_id: UUID,
    vehicle_data: VehicleBase,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new vehicle for a specific customer"""
    # Verify customer exists
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    vehicle = Vehicle(
        tenant_id=customer.tenant_id,
        customer_id=customer_id,
        **vehicle_data.model_dump(),
    )
    await sync_vehicle_nhtsa_snapshot(vehicle)
    
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.get("/{customer_id}/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def get_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific vehicle for a customer"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return VehicleResponse.model_validate(vehicle)


@router.put("/{customer_id}/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    vehicle_data: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a specific vehicle for a customer"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = vehicle_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vehicle, field, value)

    if {"vin", "year"} & set(update_data.keys()) or (vehicle.vin and vehicle.nhtsa_decoded_at is None):
        await sync_vehicle_nhtsa_snapshot(vehicle)
    
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.delete("/{customer_id}/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Delete a specific vehicle for a customer (staff only)"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    if current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    await db.delete(vehicle)
    await db.commit()

    return None


async def _get_customer_or_404_with_access(customer_id: UUID, db: AsyncSession, current_user: User) -> Customer:
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return customer


async def _clear_other_primary_contacts(db: AsyncSession, customer_id: UUID, except_contact_id: Optional[UUID] = None):
    """Enforce at most one is_primary=True contact per customer."""
    query = select(Contact).where(
        and_(Contact.customer_id == customer_id, Contact.is_primary.is_(True))
    )
    if except_contact_id is not None:
        query = query.where(Contact.id != except_contact_id)
    result = await db.execute(query)
    for other in result.scalars().all():
        other.is_primary = False


@router.get("/{customer_id}/contacts", response_model=List[ContactResponse])
async def list_customer_contacts(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all contacts for a specific customer"""
    await _get_customer_or_404_with_access(customer_id, db, current_user)

    result = await db.execute(
        select(Contact).where(Contact.customer_id == customer_id).order_by(Contact.is_primary.desc(), Contact.created_at)
    )
    contacts = result.scalars().all()
    return [ContactResponse.model_validate(c) for c in contacts]


@router.post("/{customer_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_contact(
    customer_id: UUID,
    contact_data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Create a new contact for a specific customer (staff only)"""
    customer = await _get_customer_or_404_with_access(customer_id, db, current_user)

    if contact_data.is_primary:
        await _clear_other_primary_contacts(db, customer_id)

    contact = Contact(
        tenant_id=customer.tenant_id,
        customer_id=customer_id,
        **contact_data.model_dump(),
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact)


@router.put("/{customer_id}/contacts/{contact_id}", response_model=ContactResponse)
async def update_customer_contact(
    customer_id: UUID,
    contact_id: UUID,
    contact_data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Update a specific contact for a customer (staff only)"""
    await _get_customer_or_404_with_access(customer_id, db, current_user)

    result = await db.execute(
        select(Contact).where(and_(Contact.id == contact_id, Contact.customer_id == customer_id))
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    update_fields = contact_data.model_dump(exclude_unset=True)
    if update_fields.get("is_primary"):
        await _clear_other_primary_contacts(db, customer_id, except_contact_id=contact_id)

    for field, value in update_fields.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact)


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_contact(
    customer_id: UUID,
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Delete a specific contact for a customer (staff only)"""
    await _get_customer_or_404_with_access(customer_id, db, current_user)

    result = await db.execute(
        select(Contact).where(and_(Contact.id == contact_id, Contact.customer_id == customer_id))
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    await db.commit()

    return None


@router.get("/{customer_id}/with-vehicles", response_model=CustomerWithVehiclesResponse)
async def get_customer_with_vehicles(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a customer with all their vehicles in a single response"""
    result = await db.execute(
        select(Customer)
        .options(selectinload(Customer.vehicles))
        .where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return CustomerWithVehiclesResponse.model_validate(customer)


# ============================================================================
# CUSTOMER HISTORY
# ============================================================================

@router.get("/{customer_id}/history")
async def get_customer_history(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return lifetime activity for a customer: per-RO summary + aggregate stats
    (total spend, lifetime savings, RO count)."""

    # Access check
    customer_row = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = customer_row.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch all ROs for this customer (with vehicle joined for display fields)
    orders_result = await db.execute(
        select(RepairOrder)
        .options(selectinload(RepairOrder.vehicle))
        .where(RepairOrder.customer_id == customer_id, RepairOrder.deleted_at.is_(None))
        .order_by(RepairOrder.created_at.desc())
    )
    orders = orders_result.scalars().all()
    order_ids = [o.id for o in orders]

    # Aggregate savings per RO via parts_usage (list_price - unit_price) * quantity
    savings_by_order: dict = {}
    if order_ids:
        parts_result = await db.execute(
            select(
                PartsUsage.repair_order_id,
                func.coalesce(
                    func.sum(
                        (func.coalesce(PartsUsage.list_price, PartsUsage.unit_price) - PartsUsage.unit_price)
                        * PartsUsage.quantity
                    ),
                    0,
                ),
            )
            .where(PartsUsage.repair_order_id.in_(order_ids))
            .group_by(PartsUsage.repair_order_id)
        )
        for ro_id, saving in parts_result.all():
            savings_by_order[ro_id] = float(saving or 0)

    completed_statuses = {"completed", "invoiced", "paid"}

    items = []
    lifetime_savings = 0.0
    lifetime_spend = 0.0
    completed_count = 0
    for o in orders:
        saving = savings_by_order.get(o.id, 0.0)
        total = float(o.total_cost or 0)
        is_completed = o.status.value if hasattr(o.status, "value") else str(o.status)
        if is_completed in completed_statuses:
            completed_count += 1
            lifetime_spend += total
            lifetime_savings += saving
        v = o.vehicle
        items.append({
            "id": str(o.id),
            "order_number": o.order_number,
            "status": is_completed,
            "vehicle_make": v.make if v else "",
            "vehicle_model": v.model if v else "",
            "vehicle_year": v.year if v else None,
            "vehicle_unit_number": v.unit_number if v else None,
            "total_cost": f"{total:.2f}",
            "savings": f"{saving:.2f}",
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "work_completed_at": o.work_completed_at.isoformat() if o.work_completed_at else None,
        })

    return {
        "items": items,
        "stats": {
            "total_orders": len(orders),
            "completed_orders": completed_count,
            "lifetime_spend": f"{lifetime_spend:.2f}",
            "lifetime_savings": f"{lifetime_savings:.2f}",
        },
    }


@router.get("/{customer_id}/history/{order_id}")
async def get_customer_history_detail(
    customer_id: UUID,
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Compact detail for a single RO in customer history: labor, parts, mechanic,
    amount paid, notes."""

    result = await db.execute(
        select(RepairOrder)
        .where(and_(
            RepairOrder.id == order_id,
            RepairOrder.customer_id == customer_id,
            RepairOrder.deleted_at.is_(None),
        ))
        .options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Repair order not found")
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    mechanic_name = None
    if order.assigned_mechanic_id:
        mech_row = await db.execute(select(User).where(User.id == order.assigned_mechanic_id))
        mech = mech_row.scalar_one_or_none()
        if mech:
            mechanic_name = f"{mech.first_name} {mech.last_name}".strip()

    invoice_row = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_row.scalar_one_or_none()
    amount_paid = None
    if invoice and invoice.paid_at is not None:
        amount_paid = f"{float(invoice.total_amount or 0):.2f}"

    labor = [
        {
            "id": str(li.id),
            "description": li.description,
            "hours": f"{float(li.hours or 0):.2f}",
            "hourly_rate": f"{float(li.hourly_rate or 0):.2f}",
            "total_cost": f"{float(li.total_cost or 0):.2f}",
        }
        for li in order.labor_items
    ]
    parts = [
        {
            "id": str(pu.id),
            "name": pu.inventory_item.name if pu.inventory_item else None,
            "sku": pu.inventory_item.sku if pu.inventory_item else None,
            "quantity": pu.quantity,
            "unit_price": f"{float(pu.unit_price or 0):.2f}",
            "total_price": f"{float(pu.total_price or 0):.2f}",
        }
        for pu in order.parts_usage
    ]

    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "mechanic_name": mechanic_name,
        "amount_paid": amount_paid,
        "total_cost": f"{float(order.total_cost or 0):.2f}",
        "customer_notes": order.customer_notes,
        "internal_notes": order.internal_notes,
        "labor": labor,
        "parts": parts,
    }


# ============================================================================
# VIN DECODER ENDPOINT
# ============================================================================

@router.get("/vin/decode/{vin}", response_model=VINDecodeResult)
async def decode_vehicle_vin(
    vin: str,
    model_year: Optional[int] = Query(None, description="Optional model year for better accuracy"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Decode a VIN using the free NHTSA vPIC API.
    Returns vehicle make, model, year, and other specifications.
    """
    try:
        result = await decode_vin(vin, model_year)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to decode VIN: {str(e)}",
        )
