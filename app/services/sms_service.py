import logging
import httpx
from app.core.config import settings

logger = logging.getLogger("endra_sms_service")


class SMSService:
    SLING_BASE_URL = "https://app.sling.com.ng/api/v1/send-sms"

    @staticmethod
    async def send_otp_sms(to_phone_number: str, otp_code: str) -> bool:
        """Dispatches a 6-digit OTP using the Transactional Sender ID."""
        body_text = f"Your ENDRA verification code is {otp_code}. It expires in 5 minutes. Do not share this code with anyone."
        return await SMSService._dispatch_sling_sms(
            to_phone_number, body_text, sender=settings.SLING_TRANSACTIONAL_SENDER
        )

    @staticmethod
    async def send_sos_alert_sms(to_phone_number: str, user_name: str, location: str = "Green Estate") -> bool:
        """Dispatches an emergency SOS alert using the Transactional Sender ID (priority delivery)."""
        body_text = f"SOS Alert: An emergency request has been triggered at {location} by {user_name}. Open ENDRA to view the incident and respond."
        return await SMSService._dispatch_sling_sms(
            to_phone_number, body_text, sender=settings.SLING_TRANSACTIONAL_SENDER
        )

    @staticmethod
    async def _dispatch_sling_sms(to_phone_number: str, body_text: str, sender: str) -> bool:
        payload = {
            "to": to_phone_number,
            "message": body_text,
            "sender": sender,
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

            if response.status_code == 200:
                logger.info(f"Sling SMS dispatched successfully to {to_phone_number} using sender {sender}")
                return True
            else:
                logger.error(f"Sling SMS Error: Status {response.status_code} | Payload: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to transmit SMS via Sling API: {str(e)}")
            return False