from fastapi import APIRouter
from app.api.v1.endpoints import auth, customers, vehicles, repair_orders, inventory, dashboard, services, appointments, payments, mechanics, suppliers, quotes, invoices, stripe_connect, stripe_webhooks

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(repair_orders.router, prefix="/repair-orders", tags=["repair-orders"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["appointments"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(mechanics.router, prefix="/mechanics", tags=["mechanics"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
api_router.include_router(stripe_connect.router, prefix="/stripe/connect", tags=["stripe-connect"])
api_router.include_router(stripe_webhooks.router, prefix="/webhooks/stripe", tags=["webhooks"])
