from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    NATS_URL: str = "nats://nats:4222"
    LITELLM_BASE_URL: str
    LITELLM_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    JWT_SECRET: str
    CORS_ORIGINS: str = "http://localhost:5173"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEFAULT_DOMAIN_TYPE: str = "health"
    LITELLM_MODEL: str = "openai/gpt-4o-mini"
    LITELLM_SUMMARY_MODEL: str = "openai/gpt-4o-mini"
    GIGACHAT_AUTH_KEY: str = ""
    GIGACHAT_MODEL: str = "GigaChat"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
