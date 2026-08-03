##Email Verification via otp
import httpx
import logging
from app.core.config import settings

logger = logging.getLogger("endra_email_service")


class EmailService:
    @staticmethod
    async def send_otp_email(to_email: str, recipient_name: str, otp_code: str) -> bool:
        """
        Asynchronously triggers a 6-digit OTP code email via ZeptoMail infrastructure.
        """
        payload = {
            "from": {"address": settings.ZEPTOMAIL_FROM_EMAIL},
            "to": [
                {
                    "email_address": {
                        "address": to_email,
                        "name": recipient_name
                    }
                }
            ],
            "subject": f"{otp_code} is your ENDRA verification code",
            "htmlbody": f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a; background-color: #0d0d0d; border-radius: 8px;">
                <div style="text-align: center; margin-bottom: 24px;">
                    <h2 style="color: #ffffff; margin: 0; font-size: 24px; tracking: tight;">ENDRA Security</h2>
                </div>
                <div style="background-color: #1a1a1a; border-radius: 8px; padding: 20px; border: 1px solid #2a2a2a; text-align: center;">
                    <p style="color: #a1a1aa; font-size: 14px; margin-top: 0;">Hello {recipient_name},</p>
                    <p style="color: #e4e4e7; font-size: 15px; margin-bottom: 20px;">Use the verification code below to complete your setup:</p>
                    
                    <div style="background-color: #000000; border: 1px dashed #3f3f46; border-radius: 6px; padding: 16px; margin: 20px 0;">
                        <span style="font-family: monospace; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #ffffff;">{otp_code}</span>
                    </div>
                    
                    <p style="color: #71717a; font-size: 12px; margin-bottom: 0;">This code is valid for 10 minutes. Do not share it with anyone.</p>
                </div>
            </div>
            """
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": settings.ZEPTOMAIL_API_KEY
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.ZEPTOMAIL_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )

            # --- DEBUG PRINT BLOCK ---
            print("\n================ ZEPTOMAIL RAW DEBUG ================")
            print(f"TARGET EMAIL : {to_email}")
            print(f"OTP CODE     : {otp_code}")
            print(f"STATUS CODE  : {response.status_code}")
            print(f"RAW BODY     : {response.text}")
            print("=====================================================\n")

            # Parse response payload safely
            try:
                res_data = response.json()
            except Exception:
                res_data = {}

            # ZeptoMail success indicator: HTTP 200/201/202 AND message=="OK" or code "EM_104"
            msg = res_data.get("message", "")
            data_arr = res_data.get("data", [])
            first_code = data_arr[0].get("code") if data_arr and isinstance(data_arr, list) else None

            if response.status_code in (200, 201, 202) and (msg == "OK" or first_code == "EM_104"):
                logger.info(f"OTP verification email dispatched successfully to {to_email}")
                return True
            else:
                logger.error(f"ZeptoMail Error: Status {response.status_code} - Payload: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to transmit OTP email payload down external pipe: {str(e)}")
            return False