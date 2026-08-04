from fastapi import FastAPI
from app.routers import (
    #onboarding_router,
    hardware_router,
    dashboard_router,
    message_router,
    mobile_auth_router,
    property_router,
)

app = FastAPI(
    title="ENDRA Security Platform API",
    description="Complete API Backend covering Live Streaming, Device Onboarding, AI Threat Dashboard, and Emergency Dispatch Messaging.",
    version="1.0.0"
)

# Register routers for all 4 Batches
app.include_router(mobile_auth_router.router)  # Batch 1
app.include_router(property_router.router)  # Batch 1
app.include_router(hardware_router.router)    # Batch 2
app.include_router(dashboard_router.router)   # Batch 3
app.include_router(message_router.router)   # Batch 4


@app.get("/", tags=["Health Check"])
async def root():
    return {
        "platform": "ENDRA Security Platform",
        "status": "operational",
        "version": "1.0.0"
    }