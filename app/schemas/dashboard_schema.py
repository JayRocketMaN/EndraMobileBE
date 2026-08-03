from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ThreatLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class IncidentType(str, Enum):
    FACE_MATCH = "Recognized Face"
    UNKNOWN_INTRUDER = "Unknown Intruder"
    MOTION_DETECTED = "Motion Detected"
    PERIMETER_BREACH = "Perimeter Breach"
    PANIC_TRIGGERED = "SOS Panic Trigger"


class IncidentEvent(BaseModel):
    incident_id: str = Field(..., example="inc_8820")
    timestamp: str = Field(..., example="2026-07-30T21:45:00Z")
    threat_level: ThreatLevel
    type: IncidentType
    zone: str = Field(..., example="Main Gate")
    snapshot_url: str = Field(..., example="https://cdn.endra.security/clips/inc_8820.jpg")
    confidence_score: float = Field(0.96, ge=0.0, le=1.0)


class DailySummary(BaseModel):
    date: str = Field(..., example="2026-07-30")
    total_incidents: int = 14
    threats_prevented: int = 2
    system_status: str = "Armed - Away"
    recent_events: List[IncidentEvent]


class RTSPCameraSetup(BaseModel):
    camera_name: str = Field(..., example="Backyard RTSP Feed")
    rtsp_url: str = Field(..., example="rtsp://admin:pass@192.168.1.100:554/stream1")
    zone_name: str = Field(..., example="Backyard")


class SOSDispatchTrigger(BaseModel):
    user_id: str
    current_lat: float = Field(..., example=6.4474)
    current_lng: float = Field(..., example=3.4723)
    notes: Optional[str] = "Immediate threat near primary residence entrance."