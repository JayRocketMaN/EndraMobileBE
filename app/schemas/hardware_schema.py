from enum import Enum
from typing import Optional, List
from datetime import datetime
from uuid import UUID
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
    qr_code_payload: str = Field(..., json_schema_extra={"example": "ENDRA:SN99018273:00:1A:2B:3C:4D:5E"})
    organization_id: Optional[UUID] = Field(None, json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    property_id: Optional[UUID] = Field(None, json_schema_extra={"example": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"})


class QRValidationResponse(BaseModel):
    status: str = "validated"
    activation_token: str = Field(..., json_schema_extra={"example": "sec_tok_AbCdEf123456"})
    serial_number: str = Field(..., json_schema_extra={"example": "SN99018273"})
    device_type: DeviceType = DeviceType.CAMERA
    model: str = "ENDRA-Cam-Pro-4K"


class DevicePairingRequest(BaseModel):
    device_id: str
    serial_number: str = Field(..., json_schema_extra={"example": "SN99018273"})
    zone_name: str = Field(..., json_schema_extra={"example": "Front Porch"})
    activation_token: str = Field(..., json_schema_extra={"example": "sec_tok_AbCdEf123456"})
    
    ip_address: Optional[str] = Field(None, json_schema_extra={"example": "192.168.1.50"})
    port: int = Field(554, json_schema_extra={"example": 554})
    
    stream_username: Optional[str] = Field("admin", json_schema_extra={"example": "admin"})
    stream_password: Optional[str] = Field(None, json_schema_extra={"example": "CameraPassword123"})
    
    wifi_ssid: Optional[str] = Field(None, json_schema_extra={"example": "HomeNetwork_5G"})
    wifi_password: Optional[str] = Field(None, json_schema_extra={"example": "SecretPass123"})


class DevicePairingResponse(BaseModel):
    status: str = "paired"
    device_id: str
    assigned_zone: str
    firmware_version: str = "v2.1.0-prod"
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
    property_id: Optional[str] = None
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. MANUAL SETUP SCHEMAS (ONVIF / RTSP / DVR)
# ==========================================

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
    owner_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectionValidationResponse(BaseModel):
    success: bool
    message: str
    constructed_stream_url: str
    camera: Optional[ManualCameraResponse] = None