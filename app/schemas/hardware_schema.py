from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ==========================================
# 1. SHARED ENUMS
# ==========================================

class ConnectionProtocol(str, Enum):
    ONVIF = "ONVIF"
    RTSP = "RTSP"
    DVR_NVR = "DVR/NVR"


class CameraStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTHENTICATION_FAILED = "auth_failed"
    UNREACHABLE = "unreachable"


class ConnectivityType(str, Enum):
    BLE = "Bluetooth Low Energy"
    WIFI = "Wi-Fi"
    CELLULAR = "Cellular 4G/5G"


class DeviceType(str, Enum):
    CAMERA = "Camera"
    SIREN = "Siren"
    MOTION_SENSOR = "Motion Sensor"
    DOOR_SENSOR = "Door Contact"
    PANIC_BUTTON = "Panic Button"


class StagingStatus(str, Enum):
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    PAIRED = "paired"
    EXPIRED = "expired"


# ==========================================
# 2. DISCOVERY & STAGING SCHEMAS
# ==========================================

class DeviceDiscoveryItem(BaseModel):
    device_id: str = Field(..., json_schema_extra={"example": "dev_ble_9981"})
    device_name: str = Field(..., json_schema_extra={"example": "ENDRA Outdoor Cam v2"})
    device_type: DeviceType
    signal_strength_dbm: Optional[int] = Field(-65, json_schema_extra={"example": -58})
    mac_address: Optional[str] = Field(None, json_schema_extra={"example": "AA:BB:CC:DD:EE:FF"})
    connectivity: ConnectivityType
    staging_status: StagingStatus = StagingStatus.DISCOVERED

    model_config = ConfigDict(from_attributes=True)


class QRValidationRequest(BaseModel):
    qr_code_payload: str = Field(
        ..., 
        description="Raw scanned QR string (Plain MAC/SN, Key-Value string, or JSON payload)"
    )


class QRValidationResponse(BaseModel):
    status: str = Field("validated", example="validated")
    activation_token: str = Field(..., description="Staging token generated for pairing linkage")
    identifier: str = Field(..., description="Extracted MAC address or Serial Number")
    device_type: DeviceType = DeviceType.CAMERA
    can_auto_pair: bool = Field(
        False, 
        description="True if QR contained complete network params (IP, credentials) allowing immediate zero-touch pairing."
    )

    ip_address: Optional[str] = Field(None, example="192.168.1.120")
    port: Optional[int] = Field(None, example=554)
    username: Optional[str] = Field(None, example="admin")
    password: Optional[str] = Field(None, example="Password123")
    channel: Optional[int] = Field(None, example=1)
    custom_stream_path: Optional[str] = Field(None, example="/h264/ch1/main")
    protocol: Optional[ConnectionProtocol] = Field(None, example=ConnectionProtocol.RTSP)


class DevicePairingRequest(BaseModel):
    activation_token: Optional[str] = Field(None, description="Staging token from /validate-qr")
    device_name: Optional[str] = Field("Main Entrance Camera", example="Front Gate Camera")

    ip_address: str = Field(..., example="192.168.1.120")
    port: int = Field(554, example=554)
    username: str = Field(..., example="admin")
    password: str = Field(..., example="Password123")

    channel: Optional[int] = 1
    custom_stream_path: Optional[str] = Field(None, example="/Streaming/Channels/101")
    zone_name: Optional[str] = Field("Default Zone", example="Warehouse Exterior")
    protocol: Optional[ConnectionProtocol] = ConnectionProtocol.RTSP
    mac_address: Optional[str] = Field(None, example="00:1A:2B:3C:4D:5E")
    serial_number: Optional[str] = Field(None, example="DS-2026-99018")


class QrDevicePairingRequest(DevicePairingRequest):
    activation_token: str


class DevicePairingResponse(BaseModel):
    status: str = Field("paired", example="paired")
    camera_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")
    device_name: str = Field(..., example="Front Gate Camera")
    assigned_zone: str = Field(..., example="Warehouse Exterior")
    constructed_stream_url: str = Field(..., example="rtsp://admin:Password123@192.168.1.120:554/h264/ch1/main")
    is_online: bool = True


class DiscoveredDeviceResponse(BaseModel):
    id: str
    device_id: str
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    device_name: str
    device_type: DeviceType
    connectivity: ConnectivityType
    signal_strength_dbm: Optional[int] = None
    staging_status: StagingStatus
    activation_token: Optional[str] = None
    last_known_ip: Optional[str] = None
    last_known_port: int
    firmware_version: Optional[str] = None
    organization_id: Optional[str] = None
    property_id: Optional[int] = None
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. CAMERA SCHEMAS (UNIFIED ACTIVE & MANUAL)
# ==========================================

class CameraResponse(BaseModel):
    id: str
    camera_name: str
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    assigned_zone: str
    protocol: ConnectionProtocol
    ip_address: str
    port: int
    channel: Optional[int] = 1
    custom_stream_path: Optional[str] = None
    username: str
    stream_url: str
    status: CameraStatus
    is_active: bool
    is_ptz: bool
    owner_id: Optional[int] = None
    property_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManualCameraSetupRequest(BaseModel):
    protocol: ConnectionProtocol = ConnectionProtocol.ONVIF
    ip_address: str = Field(..., json_schema_extra={"example": "192.168.1.40"})
    port: int = Field(default=554, json_schema_extra={"example": 554})
    channel: Optional[int] = Field(default=1, json_schema_extra={"example": 1})
    username: str = Field(..., json_schema_extra={"example": "admin"})
    password: str = Field(..., json_schema_extra={"example": "password123"})
    stream_url: Optional[str] = Field(None, json_schema_extra={"example": "rtsp://192.168.1.40/live"})
    camera_name: str = Field(..., json_schema_extra={"example": "Store Entrance"})


class ManualCameraResponse(BaseModel):
    id: str
    camera_name: str
    protocol: ConnectionProtocol
    ip_address: str
    port: int
    channel: Optional[int] = None
    username: str
    stream_url: Optional[str] = None
    status: CameraStatus
    is_active: bool
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CameraMetadataUpdateRequest(BaseModel):
    camera_name: Optional[str] = None
    assigned_zone: Optional[str] = None
    is_ptz: Optional[bool] = None
    retention_days: Optional[int] = None


class CameraUpdateRequest(BaseModel):
    camera_name: Optional[str] = Field(None, example="Front Entrance Camera")
    ip_address: Optional[str] = Field(None, example="192.168.1.120")
    port: Optional[int] = Field(None, example=554)
    channel: Optional[int] = Field(None, example=1)
    username: Optional[str] = Field(None, example="admin")
    password: Optional[str] = Field(None, example="Secret123!")
    custom_stream_path: Optional[str] = Field(None, example="live/ch0")
    assigned_zone: Optional[str] = Field(None, example="Warehouse A")

    model_config = ConfigDict(from_attributes=True)


class ConnectionValidationResponse(BaseModel):
    success: bool
    message: str
    constructed_stream_url: str
    camera: Optional[ManualCameraResponse] = None