import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base # Adjust this import path to match where your Base class sits

class RegistrationStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"

class CameraStatus(str, PyEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    PROVISIONING = "provisioning"


class PendingRegistration(Base):
    """
    Staging/Isolation table for hardware scanned via Barcode/QR code.
    Ensures state isolation until network configuration is completed.
    """
    __tablename__ = "pending_registrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    serial_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    brand: Mapped[str] = mapped_column(String(50), default="ENDRA")
    location_zone: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    
    # Cryptographic validation pairing token to prevent brute-forcing
    registration_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus), 
        default=RegistrationStatus.PENDING, 
        server_default="PENDING"
    )
    
    # Multi-tenant scoping foreign keys (adjust cascade rules as needed)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=True
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("properties.id", ondelete="CASCADE"), 
        nullable=True
    )

    # Lifespan Management
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP")
    )


class CameraNode(Base):
    """
    Core operational model for activated enterprise cameras.
    Maps directly to streams processed by your cloud & local go2rtc instances.
    """
    __tablename__ = "camera_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    serial_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    mac_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    brand: Mapped[str] = mapped_column(String(50), default="ENDRA")
    device_name: Mapped[str] = mapped_column(String(150), nullable=False)
    location_zone: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    
    # Network Layer Sockets
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False) # Supports IPv4 and IPv6 lengths
    port: Mapped[int] = mapped_column(Integer, default=554, server_default="554")
    
    # Stream Access Configuration (Passwords stored encrypted)
    stream_username: Mapped[str] = mapped_column(String(100), default="admin", server_default="admin")
    stream_password_encrypted: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Unique string path used by go2rtc (e.g. tenant_001_cam_sn12345)
    stream_identifier: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus), 
        default=CameraStatus.OFFLINE, 
        server_default="OFFLINE"
    )

    # Multi-tenant corporate structure mapping
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=True
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("properties.id", ondelete="CASCADE"), 
        nullable=True
    )

    # Performance Monitoring Telemetry Telemetry
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP")
    )
