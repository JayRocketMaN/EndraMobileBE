import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum
from app.core.database import Base  # Adjust to your Declarative Base import path

class AIEventType(str, enum.Enum):
    LOITERING_DETECTED = "LOITERING_DETECTED"
    SUSPICIOUS_OBJECT = "SUSPICIOUS_OBJECT"
    ANOMALOUS_BEHAVIOR = "ANOMALOUS_BEHAVIOR"
    CROWD_SURGE = "CROWD_SURGE"
    VLM_ALERT = "VLM_ALERT"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"

class AIEvent(Base):
    __tablename__ = "ai_events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, index=True, nullable=False)
    event_type = Column(String, nullable=False)  # Stores string representation of AIEventType
    confidence_score = Column(Float, nullable=False)
    snapshot_url = Column(String, nullable=True)
    video_clip_url = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))