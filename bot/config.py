from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    bot_token: str
    bot_password: str

    # Anthropic
    anthropic_api_key: str

    # Firecrawl
    firecrawl_api_key: str

    # PostgreSQL
    database_url: str

    # Redis
    redis_url: str

    # Voyage
    # voyage_api_key: str
    voyage_api_key: str = ""

    # Webhook
    webhook_url: str = ""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# assert settings.voyage_api_key, "VOYAGE_API_KEY is missing"
#
# print("VOYAGE KEY LOADED:", settings.voyage_api_key[:10])