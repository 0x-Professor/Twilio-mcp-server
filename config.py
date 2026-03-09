"""Configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Twilio credentials — get from console.twilio.com
    account_sid: str = Field(..., alias="TWILIO_ACCOUNT_SID")
    auth_token: str = Field(..., alias="TWILIO_AUTH_TOKEN")
    from_number: str = Field(..., alias="TWILIO_FROM_NUMBER")   # E.164 e.g. +15551234567

    # Optional: Messaging Service SID for advanced routing (leave blank to use from_number)
    messaging_service_sid: str = Field("", alias="TWILIO_MESSAGING_SERVICE_SID")

    # Webhook security — Twilio signs every inbound webhook
    webhook_auth_token: str = Field("", alias="TWILIO_WEBHOOK_AUTH_TOKEN")

    # Internal SQLite db for received messages
    db_path: str = Field("inbox.db", alias="TWILIO_DB_PATH")

    # Webhook server port (used inside Docker)
    webhook_port: int = Field(8080, alias="WEBHOOK_PORT")

    model_config = {"populate_by_name": True, "env_file": ".env"}


settings = Settings()
