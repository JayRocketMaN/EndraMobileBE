import httpx
import logging
import base64
from app.core.config import settings

logger = logging.getLogger("endra_sms_service")


class SMSService:
    @staticmethod
    async def send_otp_sms(to_phone_number: str, otp_code: str) -> bool:
        """
        Asynchronously dispatches a 6-digit OTP code via Twilio SMS API.
        """
        # Twilio API Endpoint
        twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        
        # Form-encoded payload expected by Twilio API
        payload = {
            "To": to_phone_number,
            "From": settings.TWILIO_PHONE_NUMBER,
            "Body": f"Your ENDRA Security verification code is: {otp_code}. Valid for 10 minutes."
        }
        
        # HTTP Basic Authentication header (Account SID + Auth Token)
        auth_string = f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}"
        encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    twilio_url,
                    data=payload,
                    headers=headers,
                    timeout=10.0
                )

            # --- DEBUG PRINT BLOCK ---
            print("\n================ TWILIO SMS RAW DEBUG ================")
            print(f"TARGET PHONE : {to_phone_number}")
            print(f"OTP CODE     : {otp_code}")
            print(f"STATUS CODE  : {response.status_code}")
            print(f"RAW BODY     : {response.text}")
            print("======================================================\n")

            if response.status_code in (200, 201):
                logger.info(f"OTP SMS dispatched successfully to {to_phone_number}")
                return True
            else:
                logger.error(f"Twilio SMS Error: Status {response.status_code} - Payload: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to transmit SMS payload down external pipe: {str(e)}")
            return False