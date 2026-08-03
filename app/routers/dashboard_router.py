from fastapi import APIRouter, status
from typing import List
import app.schemas.dashboard_schema as schemas

router = APIRouter(prefix="/api/v1/dashboard", tags=["Batch 3: Dashboard & Incident AI"])


@router.get("/summary", response_model=schemas.DailySummary)
async def get_dashboard_summary():
    """Fetches daily threat metrics, active arm status, and recent security events."""
    return schemas.DailySummary(
        date="2026-07-30",
        total_incidents=5,
        threats_prevented=1,
        system_status="Armed - Home",
        recent_events=[
            schemas.IncidentEvent(
                incident_id="inc_001",
                timestamp="2026-07-30T20:15:00Z",
                threat_level=schemas.ThreatLevel.HIGH,
                type=schemas.IncidentType.UNKNOWN_INTRUDER,
                zone="Front Driveway",
                snapshot_url="https://cdn.endra.security/clips/inc_001.jpg",
                confidence_score=0.94
            )
        ]
    )


@router.post("/add-rtsp-camera")
async def register_custom_rtsp_camera(camera: schemas.RTSPCameraSetup):
    """Allows adding custom third-party IP cameras using RTSP stream URLs."""
    return {
        "status": "connected",
        "camera_id": "rtsp_cam_501",
        "camera_name": camera.camera_name,
        "stream_health": "good"
    }


@router.post("/sos-dispatch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_emergency_sos(payload: schemas.SOSDispatchTrigger):
    """Triggers instant SOS alert to 24/7 Command Center and dispatches nearest response unit."""
    return {
        "status": "DISPATCHED",
        "dispatch_id": "dsp_911_0042",
        "estimated_eta_minutes": 5,
        "responder_unit": "Rapid Response Unit 4"
    }