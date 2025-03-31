# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    # Security
    SECRET_KEY = os.getenv(
        "SECRET_KEY", "default-secret-key-for-dev-only"
    )  # Fallback for dev

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL is not set in the environment variables.")
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Disable to improve performance

    # Mail settings
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")  # Default to Gmail SMTP
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))  # Default to TLS port
    MAIL_USE_TLS = True  # Use TLS for Gmail
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print(
            "Warning: MAIL_USERNAME or MAIL_PASSWORD not set. Email functionality will be disabled."
        )

    # Optional: Debug mode (set via environment or default to False)
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")


# For production, you might want a subclass like this:
class ProductionConfig(Config):
    DEBUG = False
    # Add production-specific settings if needed (e.g., SSL for mail)


# For development (current setup uses this implicitly)
class DevelopmentConfig(Config):
    DEBUG = True
