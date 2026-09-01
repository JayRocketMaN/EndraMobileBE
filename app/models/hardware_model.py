import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


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
    DISCOVERED = "discovered"  # Discovered via BLE or Wi-Fi scan
    VALIDATED = "validated"    # QR code validated & token issued
    PAIRED = "paired"          # Fully paired to user/property
    EXPIRED = "expired"        # Staging session timed out


class OnboardingMethod(str, Enum):
    MANUAL = "manual"
    QR_CODE = "qr_code"
    AUTO_DISCOVERY = "auto_discovery"


# Helper function to serialize Enum values safely to PostgreSQL native ENUMs
def enum_values(enum_cls):
    return lambda obj: [e.value for e in obj]


# ==========================================
# 2. DISCOVERED & STAGED DEVICES MODEL
# ==========================================

class DiscoveredDevice(Base):
    """Caches discovered BLE/Wi-Fi devices & staged QR code sessions to allow quick reconnects and auto-pairing."""
    __tablename__ = "discovered_devices"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String, 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )

    # Identifiers
    device_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    serial_number: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    device_name: Mapped[str] = mapped_column(String, default="Unconfigured Device", nullable=False)
    maker: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Device Categories
    device_type: Mapped[DeviceType] = mapped_column(
        SQLEnum(DeviceType, values_callable=enum_values(DeviceType)), 
        default=DeviceType.CAMERA, 
        nullable=False
    )
    connectivity: Mapped[ConnectivityType] = mapped_column(
        SQLEnum(ConnectivityType, values_callable=enum_values(ConnectivityType)), 
        default=ConnectivityType.WIFI, 
        nullable=False
    )
    signal_strength_dbm: Mapped[Optional[int]] = mapped_column(Integer, default=-65, nullable=True)

    # Onboarding Staging & Verification
    staging_status: Mapped[StagingStatus] = mapped_column(
        SQLEnum(StagingStatus, values_callable=enum_values(StagingStatus)), 
        default=StagingStatus.DISCOVERED, 
        nullable=False
    )
    activation_token: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    can_auto_pair: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Staged Network & Connection Parameters (Extracted from Full QR or Scan)
    last_known_ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_known_port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    cached_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached_custom_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String, default="v2.1.0-prod", nullable=True)

    # Multi-tenant Scopes
    organization_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("user_properties.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    discovered_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("mobile_users.id", ondelete="CASCADE"), 
        nullable=True
    )

    # Timestamps
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )


# ==========================================
# 3. UNIFIED ACTIVE CAMERA MODEL
# ==========================================

class Camera(Base):
    """Stores all active, paired cameras (QR, Auto-Discovered, or Manual) integrated into the VideoPipeline."""
    __tablename__ = "cameras"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String, 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )

    # Hardware & Basic Info
    camera_name: Mapped[str] = mapped_column(String, nullable=False)
    mac_address: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    assigned_zone: Mapped[str] = mapped_column(String, default="Default Zone", nullable=False)
    
    protocol: Mapped[ConnectionProtocol] = mapped_column(
        SQLEnum(ConnectionProtocol, values_callable=enum_values(ConnectionProtocol)), 
        default=ConnectionProtocol.RTSP, 
        nullable=False
    )
    
    onboarding_method: Mapped[OnboardingMethod] = mapped_column(
        SQLEnum(OnboardingMethod, values_callable=enum_values(OnboardingMethod)),
        default=OnboardingMethod.MANUAL,
        nullable=False
    )

    # Network Details (Made Optional for pure custom RTSP stream URLs)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer, default=1, nullable=True)
    custom_stream_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Credentials (Made Optional for unauthenticated RTSP feeds)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Live Feed URI & Pipeline Config
    stream_url: Mapped[str] = mapped_column(String, nullable=False)

    # System Status & Metadata
    status: Mapped[CameraStatus] = mapped_column(
        SQLEnum(CameraStatus, values_callable=enum_values(CameraStatus)), 
        default=CameraStatus.CONNECTED, 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_ptz: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Foreign Key Ownership
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("mobile_users.id", ondelete="CASCADE"), 
        nullable=True
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("user_properties.id", ondelete="SET NULL"), 
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )