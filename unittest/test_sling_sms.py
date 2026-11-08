import httpx
import os
from dotenv import load_dotenv
from app.core.config import settings

load_dotenv()

async def test_sling_connection():
    url = "https://app.sling.com.ng/api/v1/send-sms"
    
    payload = {
    "to": "2349035061392",
    "message": "Your ENDRA verification code is 123456. Expires in 5 minutes.",
    "sender": "Endratech",
    "type": "transactional"
}

    headers = {
        "Authorization": f"Bearer {settings.SLING_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    print(f"Sending test request to Sling API...")
    print(f"Sender ID : {settings.SLING_TRANSACTIONAL_SENDER}")
    print(f"Token Prefix: {settings.SLING_API_TOKEN[:6]}...\n")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
            
            if response.status_code == 200:
                print("\n SUCCESS: Sling API connection verified successfully!")
            else:
                print("\n FAILED: Check your API Token or Sender ID configuration.")
                
        except Exception as e:
            print(f"\n ERROR: Connection failed - {str(e)}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_sling_connection())