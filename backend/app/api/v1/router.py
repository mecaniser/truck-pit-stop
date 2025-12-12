from fastapi import APIRouter
from app.api.v1.endpoints import auth, customers, vehicles, repair_orders

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(repair_orders.router, prefix="/repair-orders", tags=["repair-orders"])


