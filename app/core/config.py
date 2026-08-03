from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Twilio Configuration
    TWILIO_ACCOUNT_SID: str = "AC_YOUR_TWILIO_ACCOUNT_SID"
    TWILIO_AUTH_TOKEN: str = "YOUR_TWILIO_AUTH_TOKEN"
    TWILIO_PHONE_NUMBER: str = "+1234567890"

    class Config:
        env_file = ".env"

settings = Settings()