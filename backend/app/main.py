from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title="Truck Pit Stop API",
    description="API for managing semi-truck repair garages",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # This accesses the property
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "message": "Truck Pit Stop API"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


