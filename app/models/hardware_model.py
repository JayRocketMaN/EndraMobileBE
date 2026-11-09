import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.property_model import Property


# ==========================================
# 1. SHARED ENUMS
# ==========================================

class ConnectionProtocol(str, Enum):
    ONVIF = "ONVIF"
    RTSP = "RTSP"
    DVR_NVR = "DVR/NVR"


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    AUTHENTICATION_FAILED = "AUTH_FAILED"
    UNREACHABLE = "UNREACHABLE"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_upper = value.upper()
            if val_upper in ("CONNECTED", "ONLINE"):
                return cls.ONLINE
            if val_upper in ("DISCONNECTED", "OFFLINE"):
                return cls.OFFLINE
        return None


class ConnectivityType(str, Enum):
    BLE = "BLE"
    WIFI = "WIFI"
    CELLULAR = "CELLULAR"
    

class DeviceType(str, Enum):
    CAMERA = "CAMERA"
    SIREN = "SIREN"
    MOTION_SENSOR = "MOTION_SENSOR"
    DOOR_SENSOR = "DOOR_SENSOR"
    PANIC_BUTTON = "PANIC_BUTTON"


class StagingStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATED = "VALIDATED"
    PAIRED = "PAIRED"
    EXPIRED = "EXPIRED"


class OnboardingMethod(str, Enum):
    MANUAL = "manual"
    QR_CODE = "qr_code"
    AUTO_DISCOVERY = "auto_discovery"


def enum_values(enum_cls):
    return lambda obj: [e.value for e in obj]


# ==========================================
# 2. DISCOVERED & STAGED DEVICES MODEL
# ==========================================

class DiscoveredDevice(Base):
    __tablename__ = "discovered_devices"
    __table_args__ = {'extend_existing': True}

    id: Mapped[str] = mapped_column(
        String, 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )

    device_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    serial_number: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    device_name: Mapped[str] = mapped_column(String, default="Unconfigured Device", nullable=False)
    maker: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    staging_status: Mapped[StagingStatus] = mapped_column(
        SQLEnum(StagingStatus, values_callable=enum_values(StagingStatus)), 
        default=StagingStatus.DISCOVERED, 
        nullable=False
    )
    activation_token: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    can_auto_pair: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_known_ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_known_port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    http_port: Mapped[Optional[int]] = mapped_column(Integer, default=80, nullable=True)
    verification_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached_custom_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String, default="v2.1.0-prod", nullable=True)

    organization_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Mandatory property link
    property_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("user_properties.id", ondelete="CASCADE"), 
        nullable=False
    )
    
    property: Mapped["Property"] = relationship(
        "Property", 
        back_populates="discovered_devices"
    )
    
    discovered_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("mobile_users.id", ondelete="CASCADE"), 
        nullable=True
    )

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
    __tablename__ = "cameras"
    __table_args__ = {'extend_existing': True}

    id: Mapped[str] = mapped_column(
        String, 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )

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

    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer, default=1, nullable=True)
    custom_stream_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stream_url: Mapped[str] = mapped_column(String, nullable=False)

    status: Mapped[CameraStatus] = mapped_column(
        SQLEnum(CameraStatus, values_callable=enum_values(CameraStatus)), 
        default=CameraStatus.ONLINE, 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_ptz: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("mobile_users.id", ondelete="CASCADE"), 
        nullable=True
    )
    
    # Mandatory property link enforcing One-to-Many
    property_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("user_properties.id", ondelete="CASCADE"), 
        nullable=False
    )

    property: Mapped["Property"] = relationship(
        "Property", 
        back_populates="cameras"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )