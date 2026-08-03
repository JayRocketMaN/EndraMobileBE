from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SystemState(str, Enum):
    ARMED_AWAY = "Armed - Away"
    ARMED_HOME = "Armed - Home"
    DISARMED = "Disarmed"
    NIGHT_MODE = "Night Mode"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PTZCommand(str, Enum):
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"


# --- Camera Models ---
class CameraFeed(BaseModel):
    camera_id: str
    name: str
    location: str
    is_online: bool = True
    webrtc_stream_url: str
    snapshot_url: Optional[str] = None


class CameraGridResponse(BaseModel):
    total_cameras: int
    cameras: List[CameraFeed]


class PTZControlRequest(BaseModel):
    command: PTZCommand
    step: int = Field(default=1, ge=1, le=10)


# --- System Status Models ---
class ArmSystemRequest(BaseModel):
    state: SystemState
    pin_code: Optional[str] = Field(default=None, min_length=4, max_length=6)


class SystemStatusResponse(BaseModel):
    current_state: SystemState
    last_updated: str
    updated_by: str


# --- Alert Models ---
class SecurityAlert(BaseModel):
    alert_id: str
    camera_id: str
    camera_name: str
    title: str
    message: str
    severity: AlertSeverity
    timestamp: str
    read: bool = False


class AlertListResponse(BaseModel):
    unread_count: int
    alerts: List[SecurityAlert]