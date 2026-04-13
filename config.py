"""
Configuration management for FikoHouse application
Handles environment variables, defaults, and validation
"""
import os
from functools import lru_cache
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings:
    """Application settings loaded from environment variables"""

    # Application
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./fikohouse.db"
    )

    # Security
    FERNET_KEY = os.getenv("FERNET_KEY", "").encode()
    if not FERNET_KEY or len(FERNET_KEY) < 20:
        raise ValueError(
            "FERNET_KEY environment variable is not set or invalid. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        ""
    )
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required for secure session management.")

    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    if not ADMIN_PASSWORD:
        raise ValueError("ADMIN_PASSWORD environment variable is required.")
    if len(ADMIN_PASSWORD) < 12:
        raise ValueError("ADMIN_PASSWORD must be at least 12 characters.")

    # Server
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    # CORS
    _cors_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if _cors_origins_raw:
        CORS_ALLOW_ORIGINS = [origin.strip() for origin in _cors_origins_raw.split(",") if origin.strip()]
    elif ENVIRONMENT.lower() == "development":
        CORS_ALLOW_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
    else:
        CORS_ALLOW_ORIGINS = []
    if ENVIRONMENT.lower() == "production" and not CORS_ALLOW_ORIGINS:
        raise ValueError("CORS_ALLOW_ORIGINS environment variable is required in production.")

    # Feature flags
    ALLOW_SELF_SIGNED_CERTS = os.getenv("ALLOW_SELF_SIGNED_CERTS", "false").lower() == "true"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"


@lru_cache()
def get_settings() -> Settings:
    """Get application settings (cached)"""
    return Settings()


# Export settings for easy import
settings = get_settings()
