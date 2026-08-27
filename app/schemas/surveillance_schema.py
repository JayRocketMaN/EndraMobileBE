from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.surveillance_model import AIEventType

class AIEventBase(BaseModel):
    camera_id: int
    event_type: AIEventType
    confidence_score: float
    snapshot_url: Optional[str] = None
    video_clip_url: Optional[str] = None
    details: Optional[str] = None

class AIEventCreate(AIEventBase):
    pass

class AIEventResponse(AIEventBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True