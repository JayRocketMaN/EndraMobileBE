from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import async_engine, Base

# Import models so SQLAlchemy registers them before table creation
from app.models.mobile_user_model import MobileUser
from app.models.property_model import Property
# Import other models as needed (e.g., Hardware, Dashboard, Message models)

from app.routers import (
    # onboarding_router,
    hardware_router,
    dashboard_router,
    message_router,
    mobile_auth_router,
    property_router,
)


"""@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create missing database tables on application startup
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield"""
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚨 TEMPORARILY COMMENT OUT THIS BLOCK TO PREVENT LIFESPAN BOOT CRASHES:
    # async with async_engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    
    # Keep this yield intact so FastAPI can proceed to spin up your routers
    yield 


app = FastAPI(
    title="ENDRA Security Platform API",
    description="Complete API Backend covering Live Streaming, Device Onboarding, AI Threat Dashboard, and Emergency Dispatch Messaging.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Flutter app / web clients / Swagger UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers for all 4 Batches
app.include_router(mobile_auth_router.router)  # Batch 1
app.include_router(property_router.router)     # Batch 1
app.include_router(hardware_router.router)     # Batch 2
app.include_router(dashboard_router.router)    # Batch 3
app.include_router(message_router.router)      # Batch 4


@app.get("/", tags=["Health Check"])
async def root():
    return {
        "platform": "ENDRA Security Platform",
        "status": "operational",
        "version": "1.0.0"
    }