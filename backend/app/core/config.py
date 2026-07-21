from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
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
    # Keep each web process within a predictable connection budget. These values
    # apply only to PostgreSQL; SQLite keeps its driver-appropriate defaults so
    # local development and the test suite remain lightweight.
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1)
    DATABASE_MAX_OVERFLOW: int = Field(default=5, ge=0)
    DATABASE_POOL_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    DATABASE_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=1)
    DATABASE_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    DATABASE_STATEMENT_TIMEOUT_MS: int = Field(default=15000, ge=1)
    DATABASE_LOCK_TIMEOUT_MS: int = Field(default=5000, ge=1)
    DATABASE_IDLE_TRANSACTION_TIMEOUT_MS: int = Field(default=30000, ge=1)

    # Error persistence is best-effort: it must never consume the entire pool
    # or delay an error response while the primary database is unhealthy.
    ERROR_LOG_PERSIST_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0)
    ERROR_LOG_PERSIST_MAX_CONCURRENCY: int = Field(default=2, ge=1)
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    MAX_REQUEST_BODY_BYTES: int = 15 * 1024 * 1024  # 15MB, allows 10MB photos plus multipart overhead
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
    
    # Stripe Connect. Client ID/redirect URI remain only for deployments that
    # still have historical Standard OAuth connections; new accounts use
    # Stripe-hosted onboarding and do not depend on either value.
    STRIPE_CONNECT_WEBHOOK_SECRET: str = ""
    STRIPE_CONNECT_CLIENT_ID: str = ""
    STRIPE_CONNECT_REDIRECT_URI: str = ""
    STRIPE_CONNECT_OAUTH_STATE_TTL_SECONDS: int = Field(default=600, ge=60, le=1800)
    PLATFORM_FEE_PERCENT: float = 1.5

    # QuickBooks Online OAuth. The encryption key must be a Fernet key and is
    # intentionally separate from SECRET_KEY so key rotation is scoped to
    # provider credentials rather than application sessions.
    QUICKBOOKS_CLIENT_ID: str = ""
    QUICKBOOKS_CLIENT_SECRET: str = ""
    QUICKBOOKS_REDIRECT_URI: str = ""
    QUICKBOOKS_TOKEN_ENCRYPTION_KEY: str = ""
    QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN: str = ""
    QUICKBOOKS_HTTP_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=60)
    QUICKBOOKS_OAUTH_STATE_TTL_SECONDS: int = Field(default=600, ge=60, le=1800)
    
    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    DEVELOPMENT_PHONE_NUMBER: str = ""
    
    # Resend
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@dieselbridge.network"

    # Provider outbox. Keep delivery disabled until a dedicated Celery worker
    # is deployed; enabled routes otherwise preserve their current synchronous
    # behavior instead of queueing messages that nobody can process.
    PROVIDER_OUTBOX_ENABLED: bool = False
    PROVIDER_OUTBOX_BATCH_SIZE: int = Field(default=20, ge=1, le=100)
    PROVIDER_OUTBOX_LEASE_SECONDS: int = Field(default=90, ge=30, le=900)
    PROVIDER_OUTBOX_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    PROVIDER_OUTBOX_RETRY_BASE_SECONDS: int = Field(default=30, ge=1, le=3600)
    PROVIDER_OUTBOX_RETRY_MAX_SECONDS: int = Field(default=900, ge=1, le=86400)
    PROVIDER_OUTBOX_EMAIL_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0, le=60)
    
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
        # .env carries values for standalone scripts outside this Settings
        # model (e.g. ETS_EMAIL/ETS_PASSWORD for the Easy Truck Shop import
        # tooling, which reads os.environ directly) — don't fail app/CLI
        # startup just because .env has keys this model doesn't declare.
        extra = "ignore"


settings = Settings()
