"""
Application configuration using Pydantic Settings
"""
from typing import List, Optional, Union
import json
from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore unknown env vars to avoid test env collisions
    )

    # Project
    PROJECT_NAME: str = "Chrono Scraper"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48
    ALGORITHM: str = "HS256"
    
    # Admin Security Configuration
    ADMIN_IP_WHITELIST: List[str] = []  # Empty list allows all IPs
    ADMIN_IP_BLACKLIST: List[str] = []  # Explicitly blocked IPs
    ADMIN_REQUIRE_2FA: bool = True  # Require 2FA for admin users
    ADMIN_SESSION_TIMEOUT_MINUTES: int = 30  # Admin session timeout
    ADMIN_MAX_CONCURRENT_SESSIONS: int = 3  # Max concurrent admin sessions
    ADMIN_MAX_LOGIN_ATTEMPTS: int = 3  # Max failed login attempts before lockout
    ADMIN_LOCKOUT_DURATION_MINUTES: int = 30  # Account lockout duration
    ADMIN_PASSWORD_MIN_LENGTH: int = 12  # Minimum password length for admins
    ADMIN_PASSWORD_REQUIRE_UPPERCASE: bool = True
    ADMIN_PASSWORD_REQUIRE_LOWERCASE: bool = True
    ADMIN_PASSWORD_REQUIRE_DIGITS: bool = True
    ADMIN_PASSWORD_REQUIRE_SPECIAL: bool = True
    ADMIN_PASSWORD_ROTATION_DAYS: int = 90  # Force password rotation
    ADMIN_ENFORCE_VPN_ONLY: bool = False  # Require VPN connection for admin access
    ADMIN_ALLOWED_VPN_RANGES: List[str] = []  # Allowed VPN IP ranges
    
    # User registration
    USERS_OPEN_REGISTRATION: bool = True
    ALLOW_INVITATION_TOKENS: bool = True
    REQUIRE_EMAIL_VERIFICATION: bool = True
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev server
        "http://127.0.0.1:5173",  # Local IP for Vite
        "http://127.0.0.1:3000",  # Local IP alternative
        "http://dl:5173",         # Network access via 'dl' hostname
        "http://dl:3000"          # Network access via 'dl' hostname alternative
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]):
        """
        Accept either a comma-separated string or a JSON list string for CORS origins
        as commonly passed via environment variables.
        """
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            # JSON list string e.g. '["http://localhost:3000","http://localhost:5173"]'
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    # Ensure all items are strings and strip whitespace
                    return [str(item).strip() for item in parsed]
                except json.JSONDecodeError:
                    # Fallback to comma-split if JSON parsing fails
                    return [i.strip() for i in v.split(",") if i.strip()]
            # Comma-separated string
            return [i.strip() for i in v.split(",") if i.strip()]
        raise ValueError("Invalid BACKEND_CORS_ORIGINS value")

    # Database
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_USER: str = "chrono_scraper"
    POSTGRES_PASSWORD: str = "chrono_scraper"
    POSTGRES_DB: str = "chrono_scraper"
    POSTGRES_PORT: int = 5432
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Celery
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    
    @field_validator("CELERY_BROKER_URL", mode="before")
    def assemble_celery_broker(cls, v: Optional[str], values) -> str:
        if v:
            return v
        return f"redis://{values.data.get('REDIS_HOST', 'redis')}:{values.data.get('REDIS_PORT', 6379)}/0"
    
    @field_validator("CELERY_RESULT_BACKEND", mode="before") 
    def assemble_celery_backend(cls, v: Optional[str], values) -> str:
        if v:
            return v
        return f"redis://{values.data.get('REDIS_HOST', 'redis')}:{values.data.get('REDIS_PORT', 6379)}/1"

    # Meilisearch
    MEILISEARCH_HOST: str = "http://meilisearch:7700"
    MEILISEARCH_MASTER_KEY: str = "RuvEMt9LztgYqdfqRFmZbT52uysNrt73ps57RZ2PRd53kjWxe2qiv9kadk9EiV5k"
    
    # Batch Synchronization Configuration
    MEILISEARCH_BATCH_SIZE: int = 100
    MEILISEARCH_BATCH_TIMEOUT: int = 30  # seconds
    MEILISEARCH_MAX_RETRIES: int = 3
    
    # Meilisearch Security Configuration
    MEILISEARCH_KEY_ROTATION_DAYS: int = 90  # Rotate project keys every 90 days
    MEILISEARCH_TENANT_TOKEN_EXPIRE_HOURS: int = 24  # Tenant tokens expire after 24 hours
    MEILISEARCH_PUBLIC_KEY_RATE_LIMIT: int = 1000  # Requests per hour for public keys
    MEILISEARCH_ADMIN_ACTIONS_ONLY: bool = True  # Use master key only for admin operations
    
    # Security Hardening Configuration
    SECURITY_LEVEL: str = "production"  # development, staging, production, high_security
    GLOBAL_RATE_LIMIT_PER_MINUTE: int = 1000
    ENABLE_SECURITY_MIDDLEWARE: bool = True
    ENABLE_HONEYPOT: bool = True
    ENABLE_THREAT_DETECTION: bool = True
    SECURITY_LOG_LEVEL: str = "INFO"
    
    # Advanced Threat Detection
    ENABLE_ANOMALY_DETECTION: bool = True
    ENABLE_BRUTE_FORCE_PROTECTION: bool = True
    ENABLE_DDoS_PROTECTION: bool = True
    ENABLE_SQL_INJECTION_PROTECTION: bool = True
    ENABLE_XSS_PROTECTION: bool = True
    THREAT_DETECTION_SENSITIVITY: str = "high"  # low, medium, high
    AUTO_BLOCK_THREATS: bool = True
    THREAT_BLOCK_DURATION_HOURS: int = 24
    
    # API Security
    API_KEY_ROTATION_DAYS: int = 90
    API_KEY_MIN_LENGTH: int = 32
    API_REQUEST_SIGNATURE_REQUIRED: bool = False
    API_RATE_LIMIT_PER_KEY_PER_HOUR: int = 1000
    API_KEY_EXPIRY_DAYS: int = 365
    
    # IP Security Configuration
    BLOCKED_IPS: List[str] = []
    TRUSTED_PROXIES: List[str] = []
    ENABLE_GEO_BLOCKING: bool = False
    ALLOWED_COUNTRIES: List[str] = ["US", "CA", "GB", "DE", "FR", "AU"]
    ENABLE_VPN_DETECTION: bool = False
    BLOCK_VPN_CONNECTIONS: bool = False
    ENABLE_TOR_DETECTION: bool = True
    BLOCK_TOR_CONNECTIONS: bool = True
    ENABLE_PROXY_DETECTION: bool = False
    BLOCK_PROXY_CONNECTIONS: bool = False
    SUSPICIOUS_IP_THRESHOLD: int = 10  # Suspicious activity threshold
    AUTO_BLOCK_SUSPICIOUS_IPS: bool = True
    
    # Security Headers Configuration
    ENABLE_HSTS: bool = True
    HSTS_MAX_AGE: int = 31536000  # 1 year
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = True
    CSP_POLICY: str = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    CSP_REPORT_URI: Optional[str] = None
    ENABLE_CSP_NONCE: bool = True
    X_FRAME_OPTIONS: str = "DENY"
    X_CONTENT_TYPE_OPTIONS: str = "nosniff"
    X_XSS_PROTECTION: str = "1; mode=block"
    REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=()"
    ENABLE_CERTIFICATE_PINNING: bool = False
    PINNED_CERTIFICATES: List[str] = []
    
    # Email
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None
    ADMIN_EMAIL: Optional[str] = None  # Admin email for user approval notifications
    
    # Mailgun Configuration
    MAILGUN_API_KEY: Optional[str] = None
    MAILGUN_DOMAIN: Optional[str] = None
    MAILGUN_API_URL: str = "https://api.mailgun.net/v3"
    MAILGUN_EU_REGION: bool = False  # Set to True if using EU region
    
    @field_validator("MAILGUN_API_URL", mode="before")
    def set_mailgun_url(cls, v: str, values) -> str:
        if values.data.get("MAILGUN_EU_REGION"):
            return "https://api.eu.mailgun.net/v3"
        return v or "https://api.mailgun.net/v3"
    
    # Superuser
    FIRST_SUPERUSER: str = "admin@chrono-scraper.com"
    FIRST_SUPERUSER_PASSWORD: str = "changeme"
    
    # Firecrawl Configuration
    FIRECRAWL_API_KEY: str = "fc-dev-key-local"
    FIRECRAWL_BASE_URL: str = "http://localhost:3002"
    FIRECRAWL_MODE: str = "auto"  # auto, local, cloud
    FIRECRAWL_LOCAL_URL: str = "http://localhost:3002"
    FIRECRAWL_TEST_API_KEY: str = "fc-test-key-for-local-development"
    FIRECRAWL_API_VERSION: str = "v2"
    FIRECRAWL_V2_BATCH_ENABLED: bool = True
    # Keep v2 batch-only for pause/stop semantics
    FIRECRAWL_V2_BATCH_ONLY: bool = True
    
    # OpenRouter Integration (alternative to OpenAI for local Firecrawl)
    FIRECRAWL_OPENROUTER_API_KEY: Optional[str] = None
    FIRECRAWL_OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Proxy Configuration
    USE_PROXY: bool = False
    PROXY_HTTP: Optional[str] = None
    PROXY_HTTPS: Optional[str] = None
    DECODO_USERNAME: Optional[str] = None
    DECODO_PASSWORD: Optional[str] = None
    DECODO_ENDPOINT: str = "gate.smartproxy.com"
    DECODO_PORT_RESIDENTIAL: int = 10001
    DECODO_PORT_DATACENTER: int = 10002
    DECODO_SESSION_LIFETIME: int = 1800
    DECODO_MAX_RETRIES: int = 3
    PROXY_ROTATION_ENABLED: bool = True
    PROXY_HEALTH_CHECK_INTERVAL: int = 300
    PROXY_FALLBACK_ENABLED: bool = True
    
    # Archive.org robustness settings
    ARCHIVE_ORG_TIMEOUT: int = 30
    ARCHIVE_ORG_MAX_RETRIES: int = 3
    SCRAPE_MAX_DURATION: int = 3600
    SCRAPE_STALE_THRESHOLD: int = 300
    
    # Wayback Machine settings
    WAYBACK_MACHINE_TIMEOUT: int = 180
    WAYBACK_MACHINE_MAX_RETRIES: int = 3
    
    # Hybrid Processing settings
    HYBRID_PROCESSING_ENABLED: bool = True
    HYBRID_TIMEOUT: int = 30
    HYBRID_MAX_CONCURRENT: int = 5
    
    # Scraping settings
    DEFAULT_REQUEST_TIMEOUT: int = 30
    DEFAULT_REQUESTS_PER_SECOND: float = 1.0
    DEFAULT_BURST_SIZE: int = 5
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    USER_AGENT: str = "chrono-scraper/2.0 (research tool)"
    
    # Rate limiting
    ENABLE_RATE_LIMITING: bool = True
    GLOBAL_RATE_LIMIT: float = 10.0  # requests per second globally
    DOMAIN_RATE_LIMIT: float = 1.0   # requests per second per domain
    
    # Entity Linking Configuration
    ENTITY_LINKING_CONFIDENCE_THRESHOLD: float = 0.8
    ENTITY_LINKING_FALLBACK_THRESHOLD: float = 0.6
    ENTITY_LINKING_SERVICE_PRIORITY: List[str] = ["wikidata", "dbpedia"]
    ENTITY_LINKING_ENABLE_WIKIDATA: bool = True
    ENTITY_LINKING_ENABLE_DBPEDIA: bool = True
    ENTITY_LINKING_BATCH_SIZE: int = 10
    ENTITY_LINKING_MAX_CONCURRENT: int = 5
    ENTITY_DEDUPLICATION_SIMILARITY_THRESHOLD: float = 0.85
    ENTITY_DEDUPLICATION_BATCH_SIZE: int = 100
    ENTITY_LINKING_CACHE_TIMEOUT: int = 86400  # 24 hours
    ENTITY_LINKING_SPACY_MODEL: str = "en_core_web_md"
    ENTITY_LINKING_AUTO_DOWNLOAD_MODELS: bool = False
    
    # LLM Configuration for user evaluation
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    
    # OpenRouter Configuration
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "qwen/qwen3-32b"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # User Approval System
    APPROVAL_TOKEN_EXPIRY_HOURS: int = 48
    SLACK_WEBHOOK_URL: Optional[str] = None
    
    # OAuth2 settings
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    OAUTH2_ENABLED: bool = False
    
    # Environment
    ENVIRONMENT: str = "development"
    TIME_ZONE: str = "Europe/Amsterdam"
    FRONTEND_URL: Optional[str] = None  # Frontend URL for production email links
    BACKEND_URL: Optional[str] = None   # Backend URL for API endpoints
    
    # Security Monitoring and SIEM Integration
    ENABLE_SECURITY_MONITORING: bool = True
    SIEM_ENDPOINT: Optional[str] = None
    SIEM_API_KEY: Optional[str] = None
    SECURITY_ALERT_EMAIL: Optional[str] = None
    SECURITY_ALERT_WEBHOOK: Optional[str] = None
    INCIDENT_RESPONSE_WEBHOOK: Optional[str] = None
    
    # Compliance and Audit
    ENABLE_COMPLIANCE_MODE: bool = True
    AUDIT_LOG_RETENTION_DAYS: int = 2555  # 7 years for SOX compliance
    ENABLE_TAMPER_PROOF_LOGGING: bool = True
    AUDIT_LOG_ENCRYPTION_KEY: Optional[str] = None
    ENABLE_AUDIT_LOG_SIGNING: bool = True
    COMPLIANCE_FRAMEWORKS: List[str] = ["GDPR", "SOX", "HIPAA", "PCI-DSS"]
    
    # 2FA/MFA Configuration
    MFA_ISSUER_NAME: str = "Chrono Scraper"
    MFA_TOTP_ALGORITHM: str = "SHA256"
    MFA_TOTP_DIGITS: int = 6
    MFA_TOTP_INTERVAL: int = 30
    MFA_BACKUP_CODES_COUNT: int = 10
    MFA_SMS_ENABLED: bool = False
    MFA_EMAIL_ENABLED: bool = True
    MFA_AUTHENTICATOR_ENABLED: bool = True


settings = Settings()