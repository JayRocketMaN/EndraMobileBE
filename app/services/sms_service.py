import logging
import httpx
from app.core.config import settings

logger = logging.getLogger("endra_sms_service")


class SMSService:
    SLING_BASE_URL = "https://app.sling.com.ng/api/v1/send-sms"

    @staticmethod
    async def send_otp_sms(to_phone_number: str, otp_code: str) -> bool:
        """Dispatches a 6-digit OTP using the ENDRAtech Transactional Sender ID."""
        body_text = f"Your ENDRA verification code is {otp_code}. It expires in 5 minutes. Do not share this code with anyone."
        sender_id = getattr(settings, "SLING_OTP_SENDER", "ENDRAtech").strip()
        return await SMSService._dispatch_sling_sms(
            to_phone_number, body_text, sender=sender_id
        )

    @staticmethod
    async def send_sos_alert_sms(to_phone_number: str, user_name: str, location: str = "Green Estate") -> bool:
        """Dispatches an emergency SOS alert using the EndraSOS Transactional Sender ID (priority delivery)."""
        body_text = f"SOS Alert: An emergency request has been triggered at {location} by {user_name}. Open ENDRA to view the incident and respond."
        sender_id = getattr(settings, "SLING_SOS_SENDER", "EndraSOS").strip()
        return await SMSService._dispatch_sling_sms(
            to_phone_number, body_text, sender=sender_id
        )

    @staticmethod
    async def _dispatch_sling_sms(to_phone_number: str, body_text: str, sender: str) -> bool:
        clean_recipient = to_phone_number.strip()

        payload = {
            "to": clean_recipient,
            "message": body_text,
            "sender": sender,
            "type": "transactional",
        }

        headers = {
            "Authorization": f"Bearer {settings.SLING_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    SMSService.SLING_BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )

            data = response.json()
            if response.status_code == 200 and data.get("status") == "success":
                msg_id = data.get("message_id", "N/A")
                logger.info(
                    f"Sling SMS dispatched successfully to {clean_recipient} using sender '{sender}' (Message ID: {msg_id})"
                )
                return True
            else:
                logger.error(
                    f"Sling API Error [HTTP {response.status_code}]: {data.get('details', data)}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to transmit SMS via Sling API: {str(e)}")
            return False