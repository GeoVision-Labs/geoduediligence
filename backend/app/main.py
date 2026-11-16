import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router as api_router, public_router
from .api.b2b_routes import router as b2b_router
from .api.tile_routes import router as tile_router

app = FastAPI(
    title="GeoDueDiligence API",
    description="Autonomous B2B Land Intelligence & Spatial Due Diligence Platform for Visakhapatnam Metropolitan Region (VMRDA 2041 - 7,328 km²)",
    version="1.1.0"
)

# Attach rate limit response headers if available on request state
@app.middleware("http")
async def rate_limit_header_middleware(request: Request, call_next):
    response = await call_next(request)
    if hasattr(request.state, "rate_limits"):
        limits = request.state.rate_limits
        response.headers["X-RateLimit-Limit"] = str(limits.get("limit_minute", 300))
        response.headers["X-RateLimit-Remaining"] = str(limits.get("remaining_minute", 0))
        response.headers["X-RateLimit-Daily-Quota"] = str(limits.get("limit_day", 10000))
        response.headers["X-RateLimit-Daily-Remaining"] = str(limits.get("remaining_day", 0))
    return response

# Enable CORS for external frontend or banking integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Core API, Public Verification, B2B Institutional Underwriting, and Vector Tile routes
app.include_router(api_router)
app.include_router(public_router)
app.include_router(b2b_router)
app.include_router(tile_router)

# Mount Frontend static directory
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
