from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    slack_signing_secret: str
    slack_bot_token: str | None = None
    backend_base_url: str = "http://149.102.158.71:4445"
    backend_username: str
    backend_password: str
    default_tenant_id: str = "tenant_demo"
    request_timeout_seconds: float = 20.0
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-small-latest"
    mistral_base_url: str = "https://api.mistral.ai"
    ai_parse_timeout_seconds: float = 2.5

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
