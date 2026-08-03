from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RecipientGroup(str, Enum):
    COMMAND_CENTER = "24/7 Command Center"
    RAPID_RESPONSE = "Rapid Response Unit 4"
    ESTATE_CONTROL = "Estate Control"
    GATE_GUARDS = "Gate Guards"


class ChatMessage(BaseModel):
    message_id: Optional[str] = None
    sender_id: str = Field(..., example="usr_9021")
    sender_name: str = Field(..., example="Adaeze Okonkwo")
    recipient_group: RecipientGroup
    content: str = Field(..., example="Guard, please verify visitor at Gate 2.")
    timestamp: Optional[str] = "2026-07-30T21:46:00Z"
    attachment_url: Optional[str] = None


class ThreadSummary(BaseModel):
    thread_id: str
    recipient_group: RecipientGroup
    last_message: str
    unread_count: int
    last_activity: str