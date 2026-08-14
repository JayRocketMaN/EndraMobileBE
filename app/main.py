import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.database import async_engine, Base

# Configure logging for production/deployment tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("endra_api")

# ==========================================
# 1. MODEL IMPORTS (Explicitly Register Metadata)
# ==========================================
# Importing these registers all tables with Base.metadata before startup sync
from app.models.mobile_user_model import MobileUser, EmergencyContact
from app.models.property_model import Property
from app.models.hardware_model import DiscoveredDevice, ManualCamera


# ==========================================
# 2. ROUTER IMPORTS
# ==========================================
from app.routers import (
    hardware_router,
    dashboard_router,
    message_router,
    mobile_auth_router,
    property_router,
    websocket_router,
)


async def sync_database_schema():
    """
    Live database schema sync handler.
    Ensures all registered SQLAlchemy 2.0 models exist in PostgreSQL,
    automatically creating missing tables during application startup.
    """
    try:
        logger.info("Initializing live database schema synchronization...")
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema synchronized successfully: All tables created and verified.")
    except Exception as e:
        logger.error(f"Failed to synchronize database schema: {str(e)}")
        raise e


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically sync missing database tables on application startup
    await sync_database_schema()
    yield


app = FastAPI(
    title="ENDRA Security Platform API",
    description="Complete API Backend covering Live Streaming, Device Onboarding, AI Threat Dashboard, and Emergency Dispatch Messaging.",
    version="1.0.0",
    lifespan=lifespan,
)


# ==========================================
# CUSTOM OPENAPI METADATA (For WebSockets in Swagger UI)
# ==========================================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Manually append your WebSocket route to the OpenAPI spec
    openapi_schema["paths"]["/ws"] = {
        "get": {
            "tags": ["WebSocket Real-time Feeds"],
            "summary": "Real-time Incident & Alert Feed (WebSocket)",
            "description": "Establish a WebSocket connection (`wss://`) for live AI threat detection and emergency dispatch feeds.",
            "responses": {
                "101": {
                    "description": "Switching Protocols to WebSocket"
                }
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


# Enable CORS for Flutter mobile app, web clients, and Swagger UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 3. ROUTER REGISTRATION
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