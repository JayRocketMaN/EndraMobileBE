from fastapi import APIRouter, status
from typing import List
import app.schemas.message_schema as schemas

router = APIRouter(prefix="/api/v1/messaging", tags=["Batch 4: Dispatch & Responder Messaging"])


@router.get("/threads", response_model=List[schemas.ThreadSummary])
async def list_chat_threads():
    """Lists active communication threads with Command Center, Responders, and Gate Control."""
    return [
        schemas.ThreadSummary(
            thread_id="th_cmd_01",
            recipient_group=schemas.RecipientGroup.COMMAND_CENTER,
            last_message="Unit 4 is en route to your location.",
            unread_count=1,
            last_activity="2 mins ago"
        ),
        schemas.ThreadSummary(
            thread_id="th_gate_02",
            recipient_group=schemas.RecipientGroup.GATE_GUARDS,
            last_message="Visitor cleared for entry.",
            unread_count=0,
            last_activity="15 mins ago"
        )
    ]


@router.post("/send", status_code=status.HTTP_201_CREATED, response_model=schemas.ChatMessage)
async def send_message(message: schemas.ChatMessage):
    """Sends a direct message or alert to command center operators or local security personnel."""
    return schemas.ChatMessage(
        message_id="msg_9941",
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        recipient_group=message.recipient_group,
        content=message.content,
        timestamp="2026-07-30T21:46:44Z",
        attachment_url=message.attachment_url
    )