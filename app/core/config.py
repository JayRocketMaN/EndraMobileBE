from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Squad by GTCO Payment Gateway
    # ==========================================
    SQUAD_ENV: str = Field("sandbox", json_schema_extra={"example": "sandbox"})
    SQUAD_SANDBOX_SECRET_KEY: Optional[str] = Field(None, json_schema_extra={"example": "sandbox_sk_..."})
    SQUAD_SANDBOX_URL: str = Field(
        "https://sandbox-api-d.squadco.com",
        json_schema_extra={"example": "https://sandbox-api-d.squadco.com"}
    )
    SQUAD_LIVE_SECRET_KEY: Optional[str] = Field(None, json_schema_extra={"example": "sk_..."})
    SQUAD_LIVE_URL: str = Field(
        "https://api-d.squadco.com",
        json_schema_extra={"example": "https://api-d.squadco.com"}
    )
    SQUAD_CALLBACK_URL: str = Field(
        "http://localhost:3000/subscriptions/callback",
        json_schema_extra={"example": "https://your-domain.com/subscriptions/callback"}
    )

    @property
    def is_live_env(self) -> bool:
        return self.SQUAD_ENV.lower() in ("live", "production")

    @property
    def SQUAD_SECRET_KEY(self) -> str:
        if self.is_live_env:
            return self.SQUAD_LIVE_SECRET_KEY or ""
        return self.SQUAD_SANDBOX_SECRET_KEY or ""

    @property
    def SQUAD_BASE_URL(self) -> str:
        if self.is_live_env:
            return self.SQUAD_LIVE_URL.rstrip("/")
        return self.SQUAD_SANDBOX_URL.rstrip("/")

    @property
    def SQUAD_INITIATE_URL(self) -> str:
        return f"{self.SQUAD_BASE_URL}/transaction/initiate"

    @property
    def SQUAD_VERIFY_URL(self) -> str:
        return f"{self.SQUAD_BASE_URL}/transaction/verify"

    # ==========================================
    # Pydantic Structural Loading Behavior
    # ==========================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()