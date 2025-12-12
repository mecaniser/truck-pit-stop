from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import engine
from sqlalchemy import text

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

# Health check endpoints (before SPA routing)
@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/health/db")
async def db_health_check():
    """Check database connection"""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.scalar()
        return {
            "status": "ok",
            "database": "connected",
            "database_url": settings.DATABASE_URL.split("@")[-1].split("/")[0] if "@" in settings.DATABASE_URL else "configured"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# Serve frontend static files
# Path: /app/app/main.py -> /app -> /app/frontend/dist
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
print(f"Checking frontend dist at: {frontend_dist}")
print(f"Frontend dist exists: {frontend_dist.exists()}")
if frontend_dist.exists():
    print(f"Serving frontend from: {frontend_dist}")
    # Serve static assets (JS, CSS, etc.)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    # Serve other static files (favicon, etc.)
    static_files = ["favicon.ico", "vite.svg", "robots.txt"]
    for file in static_files:
        file_path = frontend_dist / file
        if file_path.exists():
            @app.get(f"/{file}")
            async def serve_static_file(filename: str = file):
                return FileResponse(str(file_path))
    
    # Serve index.html for root and all non-API routes (SPA routing)
    # This must be last to catch all routes
    @app.get("/")
    async def serve_root():
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"status": "ok", "message": "Truck Pit Stop API - Frontend not built"}
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve index.html for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Don't serve index.html for static assets
        if full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Don't serve index.html for health endpoints
        if full_path.startswith("health"):
            raise HTTPException(status_code=404, detail="Not found")
        
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    print(f"WARNING: Frontend dist not found at {frontend_dist}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Listing /app contents: {list(Path('/app').iterdir())}")
    # Fallback if frontend not built
    @app.get("/")
    async def root():
        return {"status": "ok", "message": "Truck Pit Stop API - Frontend not found"}
    
    @app.get("/{full_path:path}")
    async def fallback_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return {"status": "error", "message": "Frontend not built", "path": str(frontend_dist)}


