import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.database import Base, async_engine

# Configure logging for production/deployment tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("endra_api")

# ==========================================
# 1. MODEL IMPORTS (Explicitly Register Metadata)
# ==========================================
from app.models.hardware_model import Camera, DiscoveredDevice
from app.models.mobile_user_model import EmergencyContact, MobileUser
from app.models.property_model import Property

# ==========================================
# 2. ROUTER IMPORTS
# ==========================================
from app.routers import (
    dashboard_router,
    hardware_router,
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
# 3. CORS MIDDLEWARE (Configured for Credentials & Web Compatibility)
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?|https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================================
# 4. GLOBAL EXCEPTION HANDLERS
# ==========================================
# CORSMiddleware handles headers globally; removing manual CORS headers here
# prevents duplicate/conflicting header errors in the browser.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
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


# ==========================================
# 5. ROUTER REGISTRATION
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