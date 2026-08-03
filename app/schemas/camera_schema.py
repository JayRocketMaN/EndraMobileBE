from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID

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


class DeviceDiscoveryItem(BaseModel):
    device_id: str = Field(..., example="dev_ble_9981")
    device_name: str = Field(..., example="ENDRA Outdoor Cam v2")
    device_type: DeviceType
    signal_strength_dbm: int = Field(-65, example=-58)
    mac_address: str = Field(..., example="AA:BB:CC:DD:EE:FF")
    connectivity: ConnectivityType


class QRValidationRequest(BaseModel):
    qr_code_payload: str = Field(..., example="ENDRA:SN99018273:00:1A:2B:3C:4D:5E")
    # Added scopes to bind the scanned device to the correct tenant context immediately
    organization_id: Optional[UUID] = Field(None, example="123e4567-e89b-12d3-a456-426614174000")
    property_id: Optional[UUID] = Field(None, example="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d")


class DevicePairingRequest(BaseModel):
    device_id: str
    serial_number: str = Field(..., example="SN99018273")
    zone_name: str = Field(..., example="Front Porch")
    
    # Crucial additive: The token generated during QR scan used to finalize staging verification
    activation_token: str = Field(..., example="sec_tok_AbCdEf123456")
    
    # Explicit network mapping parameters matching your main Camera database profile
    ip_address: str = Field(..., example="192.168.1.50")
    port: int = Field(554, example=554)
    
    # Device authentication credentials discovered or updated during onboarding loops
    stream_username: Optional[str] = Field("admin", example="admin")
    stream_password: Optional[Optional[str]] = Field(None, example="CameraPassword123")
    
    wifi_ssid: Optional[str] = Field(None, example="HomeNetwork_5G")
    wifi_password: Optional[str] = Field(None, example="SecretPass123")


class DevicePairingResponse(BaseModel):
    status: str = "paired"
    device_id: str
    assigned_zone: str # Fixed the visual screenshot typo: corrected "stri" to "str"
    firmware_version: str = "v2.1.0-prod"
    is_online: bool = True
