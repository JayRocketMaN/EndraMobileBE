import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.hardware_model import Camera, DiscoveredDevice


class PropertyTypeEnum(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"


class Property(Base):
    __tablename__ = "user_properties"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mobile_users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    property_name: Mapped[str] = mapped_column(String(150), nullable=False)  # e.g., "My Home"
    full_address: Mapped[str] = mapped_column(String(255), nullable=False)   # e.g., "12 Adeola Way, Lekki Phase 1"
    property_type: Mapped[PropertyTypeEnum] = mapped_column(
        SQLEnum(PropertyTypeEnum, native_enum=False), default=PropertyTypeEnum.RESIDENTIAL
    )

    # GPS Location Pinned Coordinates
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- Relationships ---
    cameras: Mapped[List["Camera"]] = relationship(
        "Camera", 
        back_populates="property", 
        cascade="all, delete-orphan"
    )

    discovered_devices: Mapped[List["DiscoveredDevice"]] = relationship(
        "DiscoveredDevice", 
        back_populates="property", 
        cascade="all, delete-orphan"
    )