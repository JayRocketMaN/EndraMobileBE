from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import async_engine, Base

# ==========================================
# MODEL IMPORTS (Required for Base.metadata)
# ==========================================
from app.models.mobile_user_model import MobileUser, EmergencyContact
from app.models.property_model import Property
from app.models.hardware_model import DiscoveredDevice, ManualCamera


# ==========================================
# ROUTER IMPORTS
# ==========================================
from app.routers import (
    hardware_router,
    dashboard_router,
    message_router,
    mobile_auth_router,
    property_router,
    websocket_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create missing database tables on application startup on Render
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="ENDRA Security Platform API",
    description="Complete API Backend covering Live Streaming, Device Onboarding, AI Threat Dashboard, and Emergency Dispatch Messaging.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Flutter mobile app, web clients, and Swagger UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ROUTER REGISTRATION
# ==========================================
app.include_router(mobile_auth_router.router)
app.include_router(property_router.router)
app.include_router(hardware_router.router)
app.include_router(websocket_router.router)
app.include_router(dashboard_router.router)
app.include_router(message_router.router)


@app.get("/", tags=["Health Check"])
async def root():
    return {
        "platform": "ENDRA Security Platform",
        "status": "operational",
        "version": "1.0.0"
    }