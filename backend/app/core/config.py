import os


class Settings:
    def __init__(self) -> None:
        self.database_url = self._normalize_database_url(
            os.getenv("DATABASE_URL", "sqlite:///./dev.db")
        )
        self.cors_origins = self._parse_list(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        )
        self.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me-before-deploy")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "480"))
        self.seed_demo_users = os.getenv("SEED_DEMO_USERS", "true").strip().lower() == "true"

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
