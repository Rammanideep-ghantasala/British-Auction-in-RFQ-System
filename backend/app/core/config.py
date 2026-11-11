import os


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("APP_ENV", "production" if os.getenv("RAILWAY_ENVIRONMENT_ID") else "development")
        self.database_url = self._normalize_database_url(
            os.getenv("DATABASE_URL", "sqlite:///./dev.db")
        )
        self.cors_origins = self._parse_list(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        )
        self.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me-before-deploy")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
        self.seed_demo_users = os.getenv("SEED_DEMO_USERS", "true").strip().lower() == "true"
        self.demo_user_password = os.getenv("DEMO_USER_PASSWORD", "password123")
        self.api_rate_limit_per_minute = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "300"))
        self.auth_rate_limit_per_minute = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "20"))
        self.api_max_body_bytes = int(os.getenv("API_MAX_BODY_BYTES", str(1024 * 1024)))
        self.celery_broker_url = os.getenv(
            "CELERY_BROKER_URL",
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        )
        self.celery_result_backend = os.getenv(
            "CELERY_RESULT_BACKEND",
            os.getenv("REDIS_URL", self.celery_broker_url),
        )
        self.auction_close_scan_interval_seconds = int(
            os.getenv("AUCTION_CLOSE_SCAN_INTERVAL_SECONDS", "60")
        )
        self.rate_limit_redis_url = os.getenv("RATE_LIMIT_REDIS_URL", self.celery_broker_url if self.environment == "production" else "")
        self.trusted_proxy_cidrs = self._parse_list(os.getenv("TRUSTED_PROXY_CIDRS", ""))
        if self.environment == "production":
            if len(self.secret_key) < 32 or any(word in self.secret_key.lower() for word in ("change-me", "replace-with", "change-before")):
                raise ValueError("Production requires a random SECRET_KEY of at least 32 characters.")
            if not self.cors_origins or any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production CORS_ORIGINS must contain explicit HTTPS origins.")
            if not self.rate_limit_redis_url:
                raise ValueError("Production requires Redis for shared rate limiting.")
        if not 1 <= self.access_token_minutes <= 480:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 480.")
        if self.api_max_body_bytes < 1 or self.auction_close_scan_interval_seconds < 1:
            raise ValueError("Body size and scan interval must be positive.")

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _normalize_database_url(value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


settings = Settings()
