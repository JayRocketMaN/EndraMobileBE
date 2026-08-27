from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # ==========================================
    # Core Application Security
    # ==========================================
    SECRET_KEY: str = Field(..., json_schema_extra={"example": "your-super-secret-signature-key"})
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:3000"

    
    # ==========================================
    # PostgreSQL Configuration Data Matrix
    # ==========================================
    POSTGRES_SERVER: str = Field("localhost:5432", json_schema_extra={"example": "localhost:5432"})
    POSTGRES_USER: str = Field(..., json_schema_extra={"example": "JayRM"})
    POSTGRES_PASSWORD: str = Field(..., json_schema_extra={"example": "Buconlodge26)"})
    POSTGRES_DB: str = Field(..., json_schema_extra={"example": "project_endra"})
    DATABASE_URL: str = Field(..., json_schema_extra={"example": "postgresql+asyncpg://user:pass@host:port/db"})

    # ==========================================
    # Video & Infrastructure Encryption Keys
    # ==========================================
    CAMERA_ENCRYPTION_KEY: str = Field(..., json_schema_extra={"example": "Qw01SfAi0-ZwwT_S..."})

    # ==========================================
    # ZeptoMail Dispatch Gateway Keys
    # ==========================================
    ZEPTOMAIL_API_URL: Optional[str] = Field(None, json_schema_extra={"example": "https://zeptomail.com"})
    ZEPTOMAIL_API_KEY: Optional[str] = Field(None, json_schema_extra={"example": "Zoho-enczapikey..."})
    ZEPTOMAIL_FROM_EMAIL: str = "noreply@endratech.com"

    # ==========================================
    # Pydantic Structural Loading Behavior
    # ==========================================
    # Configured to pull from local text file and ignore unexpected background environment parameters safely
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Safety fallback mechanism
    )

settings = Settings()
