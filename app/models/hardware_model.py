import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String
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


# ==========================================
# 2. DISCOVERED & STAGED DEVICES MODEL
# ==========================================

class DiscoveredDevice(Base):
    """Caches discovered BLE/Wi-Fi devices & staged QR code sessions to allow quick reconnects."""
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
    device_name: Mapped[str] = mapped_column(String, nullable=False)

    # Device Categories
    device_type: Mapped[DeviceType] = mapped_column(SQLEnum(DeviceType), nullable=False)
    connectivity: Mapped[ConnectivityType] = mapped_column(SQLEnum(ConnectivityType), nullable=False)
    signal_strength_dbm: Mapped[Optional[int]] = mapped_column(Integer, default=-65, nullable=True)

    # Onboarding Staging & Verification
    staging_status: Mapped[StagingStatus] = mapped_column(
        SQLEnum(StagingStatus), 
        default=StagingStatus.DISCOVERED, 
        nullable=False
    )
    activation_token: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)

    # Cached Network Parameters
    last_known_ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_known_port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    firmware_version: Mapped[Optional[str]] = mapped_column(String, default="v2.1.0-prod", nullable=True)

    # Multi-tenant Scopes
    organization_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # FK target fixed to 'user_properties.id' with Integer type matching Property model
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("user_properties.id", ondelete="SET NULL"), 
        nullable=True
    )
    discovered_by_user_id: Mapped[Optional[str]] = mapped_column(
        String, 
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
# 3. MANUAL CAMERA REGISTRATION MODEL
# ==========================================

class ManualCamera(Base):
    """Stores custom IP/ONVIF/RTSP cameras added manually via the UI setup form."""
    __tablename__ = "manual_cameras"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String, 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )

    # Basic Info
    camera_name: Mapped[str] = mapped_column(String, nullable=False)
    protocol: Mapped[ConnectionProtocol] = mapped_column(
        SQLEnum(ConnectionProtocol), 
        default=ConnectionProtocol.ONVIF, 
        nullable=False
    )

    # Network Details
    ip_address: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer, default=1, nullable=True)

    # Credentials
    username: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)

    # Video Feeds
    stream_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # System Status
    status: Mapped[CameraStatus] = mapped_column(
        SQLEnum(CameraStatus), 
        default=CameraStatus.DISCONNECTED, 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Foreign Key Setup
    owner_id: Mapped[Optional[str]] = mapped_column(
        String, 
        ForeignKey("mobile_users.id", ondelete="CASCADE"), 
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