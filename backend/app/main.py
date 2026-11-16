import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router as api_router, public_router

app = FastAPI(
    title="GeoDueDiligence API",
    description="Autonomous B2B Land Intelligence & Spatial Due Diligence Platform for Visakhapatnam Metropolitan Region (VMRDA 2041 - 7,328 km²)",
    version="1.0.0"
)

# Enable CORS for external frontend or banking integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes and Public Verification routes
app.include_router(api_router)
app.include_router(public_router)

# Mount Frontend static directory
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
