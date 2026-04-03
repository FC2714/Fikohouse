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
        "dev-secret-key-change-in-production"
    )

    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Fiko070House!")

    # Application
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    # Server
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

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
