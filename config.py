import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-for-dev-only")
    if SECRET_KEY == "default-secret-key-for-dev-only" and os.getenv("FLASK_ENV") == "production":
        print("Warning: Using default SECRET_KEY in production is insecure! Please set a strong, unique key.")

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://postgres:1234567890@localhost:5432/final_inspace")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Mail settings
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("Warning: MAIL_USERNAME or MAIL_PASSWORD not set. Email functionality will be disabled.")

    # Upload folder
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Uploads')

    # Debug mode
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")

class ProductionConfig(Config):
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

current_config = os.getenv("FLASK_ENV", "development")
ConfigClass = config_by_name.get(current_config, DevelopmentConfig)