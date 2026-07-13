import os
from datetime import timedelta

from futbot_common.jwt_tokens import create_token, decode_token


class Settings:
    def __init__(self) -> None:
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://futbot:futbot@localhost:5432/futbot",
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.google_redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:8000/auth/oauth/google/callback",
        )
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
        self.refresh_token_days = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
        self.setup_token_minutes = int(os.getenv("SETUP_TOKEN_MINUTES", "30"))
        self.step_up_token_minutes = int(os.getenv("STEP_UP_TOKEN_MINUTES", "5"))

    def access_delta(self) -> timedelta:
        return timedelta(minutes=self.access_token_minutes)

    def refresh_delta(self) -> timedelta:
        return timedelta(days=self.refresh_token_days)

    def setup_delta(self) -> timedelta:
        return timedelta(minutes=self.setup_token_minutes)

    def step_up_delta(self) -> timedelta:
        return timedelta(minutes=self.step_up_token_minutes)


settings = Settings()
