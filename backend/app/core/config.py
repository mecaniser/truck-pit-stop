from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    
    # Observability
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "console"  # "json" for production, "console" for dev
    METRICS_ENABLED: bool = True  # Enable /metrics endpoint
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    MAX_REQUEST_BODY_BYTES: int = 10 * 1024 * 1024  # 10MB
    IDEMPOTENCY_MAX_CACHED_RESPONSE_BYTES: int = 1 * 1024 * 1024  # 1MB
    RATE_LIMIT_TOKEN_CACHE_TTL_SECONDS: int = 30
    RATE_LIMIT_INVALID_TOKEN_CACHE_TTL_SECONDS: int = 5
    RATE_LIMIT_TOKEN_CACHE_MAX_ENTRIES: int = 5000
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER: int = 30  # "Remember me" duration
    
    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters for security")
        return v
    
    # Cookie settings
    COOKIE_SECURE: bool = False  # Set True in production (requires HTTPS)
    COOKIE_DOMAIN: str = ""  # Leave empty for localhost
    COOKIE_SAMESITE: str = "lax"  # "strict", "lax", or "none"
    
    @property
    def COOKIE_SECURE_EFFECTIVE(self) -> bool:
        """Force secure cookies in production environment"""
        return self.ENVIRONMENT == "production" or self.COOKIE_SECURE
    
    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    
    # Stripe Connect
    STRIPE_CONNECT_WEBHOOK_SECRET: str = ""
    PLATFORM_FEE_PERCENT: float = 1.5
    
    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    DEVELOPMENT_PHONE_NUMBER: str = ""
    
    # Resend
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@dieselbridge.network"
    
    # Cloudinary (for work photos)
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Telematics / ELD (fleet GPS feed). "manual" = no external provider; truck
    # positions come from manual entry / last-known. Swap to "samsara"/"motive"/etc.
    # and supply TELEMATICS_API_KEY to enable live sync.
    TELEMATICS_PROVIDER: str = "manual"
    TELEMATICS_API_KEY: str = ""

    # Anthropic (offline description-library canonicalization)
    ANTHROPIC_API_KEY: str = ""

    # Frontend
    FRONTEND_URL: str = "http://localhost:5173"
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS_STR: str = "http://localhost:5173"
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Parse CORS_ORIGINS from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",") if origin.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
