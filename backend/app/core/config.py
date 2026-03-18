"""Application configuration"""
import secrets
from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

# Auto-generate a stable dev key so the app works without .env
_DEV_SECRET_KEY = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Gas Incident Intelligence"

    # Security — auto-generated for dev; override in .env for production
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — allow localhost by default for dev
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Database
    DATABASE_URL: str = "sqlite:///./gas_incidents.db"

    # MongoDB — default to localhost for dev
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "gas_incident_platform"
    
    # ML Models
    OCR_MODEL_PATH: str = "./models/ocr"
    CV_MODEL_PATH: str = "./models/computer_vision"
    AUDIO_MODEL_PATH: str = "./models/audio"
    
    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"
    
    # Workflow
    WORKFLOW_TIMEOUT_SECONDS: int = 300

    # Connectors
    CONNECTOR_ENCRYPTION_KEY: str = ""  # Falls back to SECRET_KEY if empty
    CONNECTOR_SYNC_ENABLED: bool = True

    # WebSocket auth behavior
    ALLOW_UNAUTHENTICATED_WEBSOCKET: bool = False

    # Tenant uploads
    TENANT_UPLOAD_DIR: str = "./uploads/tenants"

    # Seeding
    SKIP_SEED: bool = False

    # Seed passwords
    seed_admin_password: str = ""
    seed_andrew_password: str = ""
    seed_super_password: str = ""
    seed_platadmin_password: str = ""

    @model_validator(mode="after")
    def _fill_secret_key(self):
        """Auto-generate SECRET_KEY for dev if not provided in .env."""
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
            self.SECRET_KEY = _DEV_SECRET_KEY
        return self

    @property
    def connector_encryption_key(self) -> str:
        return self.CONNECTOR_ENCRYPTION_KEY or self.SECRET_KEY

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
