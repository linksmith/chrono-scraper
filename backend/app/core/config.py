"""
Application configuration using Pydantic Settings
"""
from typing import List, Optional, Union, Dict
import json
from pydantic import AnyHttpUrl, field_validator
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
    
    # Content Extraction Configuration
    USE_INTELLIGENT_EXTRACTION_ONLY: bool = False  # Bypass Firecrawl entirely, use intelligent extraction
    INTELLIGENT_EXTRACTION_CONCURRENCY: int = 10   # Concurrent extractions for intelligent system
    
    # Firecrawl Configuration (Legacy - will be deprecated)
    FIRECRAWL_API_KEY: str = "fc-dev-key-local"
    FIRECRAWL_BASE_URL: str = "http://localhost:3002"
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
    PROXY_SERVER: Optional[str] = None
    PROXY_USERNAME: Optional[str] = None
    PROXY_PASSWORD: Optional[str] = None
    DECODO_USERNAME: Optional[str] = None
    DECODO_PASSWORD: Optional[str] = None
    DECODO_ENDPOINT: str = "gate.smartproxy.com"
    DECODO_PORT_RESIDENTIAL: int = 10001
    DECODO_PORT_DATACENTER: int = 10002
    
    # Query Optimization Configuration
    QUERY_OPTIMIZATION_ENABLED: bool = True
    ENABLE_AUTOMATIC_QUERY_REWRITING: bool = True
    ENABLE_PREDICATE_PUSHDOWN: bool = True
    ENABLE_JOIN_OPTIMIZATION: bool = True
    MAX_QUERY_OPTIMIZATION_TIME_MS: int = 500
    QUERY_SIMILARITY_THRESHOLD: float = 0.8
    ENABLE_QUERY_COST_ESTIMATION: bool = True
    
    # Multi-Level Caching Configuration  
    ENABLE_MULTI_LEVEL_CACHING: bool = True
    L1_CACHE_SIZE_MB: int = 512
    L2_REDIS_CACHE_TTL_SECONDS: int = 3600
    L3_MATERIALIZED_VIEW_TTL_HOURS: int = 24
    CACHE_WARM_UP_ENABLED: bool = True
    PREDICTIVE_CACHING_ENABLED: bool = True
    CACHE_COMPRESSION_ENABLED: bool = True
    CACHE_COMPRESSION_THRESHOLD_KB: int = 1  # Compress data larger than 1KB
    ENABLE_CACHE_ANALYTICS: bool = True
    
    # Performance Monitoring Configuration
    PERFORMANCE_MONITORING_ENABLED: bool = True
    QUERY_PERFORMANCE_TRACKING_ENABLED: bool = True
    SLOW_QUERY_THRESHOLD_MS: int = 1000
    ENABLE_ANOMALY_DETECTION: bool = True
    ANOMALY_DETECTION_SENSITIVITY: str = "medium"  # low, medium, high
    PERFORMANCE_ALERT_THRESHOLDS: Dict = {
        "slow_query_percentage": 5.0,
        "error_rate_percentage": 1.0,
        "memory_usage_percentage": 80.0,
        "cpu_usage_percentage": 75.0,
        "queue_depth_threshold": 50,
        "cache_hit_rate_minimum": 70.0
    }
    
    # Adaptive Query Executor Configuration
    MAX_CONCURRENT_QUERIES: int = 100
    QUERY_TIMEOUT_SECONDS: int = 300  
    MEMORY_LIMIT_PER_QUERY_MB: int = 1024
    ENABLE_QUERY_QUEUEING: bool = True
    QUERY_PRIORITY_LEVELS: int = 5
    ENABLE_ADAPTIVE_TIMEOUT: bool = True
    ENABLE_AUTOMATIC_RETRY: bool = True
    MAX_QUERY_RETRIES: int = 3
    RETRY_BACKOFF_MULTIPLIER: float = 2.0
    
    # Resource Management Configuration
    ENABLE_RESOURCE_QUOTAS: bool = True
    DEFAULT_USER_QUERY_LIMIT_PER_HOUR: int = 1000
    DEFAULT_USER_MEMORY_LIMIT_MB: int = 512
    DEFAULT_USER_CONCURRENT_QUERIES: int = 10
    ENABLE_EMERGENCY_CIRCUIT_BREAKER: bool = True
    SYSTEM_MEMORY_THRESHOLD_PERCENT: float = 85.0
    SYSTEM_CPU_THRESHOLD_PERCENT: float = 80.0
    
    # Cache Integration Configuration
    ENABLE_CROSS_DATABASE_CACHING: bool = True
    CACHE_CONSISTENCY_LEVEL: str = "session"  # eventual, session, read_after_write, strong
    ENABLE_HYBRID_QUERY_CACHING: bool = True
    CACHE_INVALIDATION_BATCH_SIZE: int = 100
    ENABLE_CACHE_CONSISTENCY_MONITORING: bool = True
    
    # Advanced Optimization Features
    ENABLE_MACHINE_LEARNING_OPTIMIZATION: bool = False  # Requires ML models
    ML_QUERY_PREDICTION_ENABLED: bool = False
    ML_CACHE_WARMING_ENABLED: bool = False
    ENABLE_COST_BASED_OPTIMIZATION: bool = True
    OPTIMIZATION_LEARNING_RATE: float = 0.1
    
    # Performance Targets and SLAs
    TARGET_QUERY_RESPONSE_TIME_MS: int = 500
    TARGET_CACHE_HIT_RATE_PERCENT: float = 80.0
    TARGET_SYSTEM_AVAILABILITY_PERCENT: float = 99.9
    SLA_VIOLATION_ALERT_THRESHOLD: int = 3  # Consecutive violations before alert
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
    
    # Archive Source Configuration
    # Comprehensive settings for multi-archive support and intelligent source selection
    
    # Default Archive Source Settings
    # Primary archive source for new projects ("wayback", "commoncrawl", "auto")
    DEFAULT_ARCHIVE_SOURCE: str = "wayback"
    # Enable automatic fallback to secondary archives when primary fails
    DEFAULT_FALLBACK_ENABLED: bool = True
    # Enable intelligent source selection based on URL patterns and availability
    ARCHIVE_SOURCE_AUTO_DETECTION: bool = True
    
    # Common Crawl Settings
    # Timeout for Common Crawl API queries (seconds)
    COMMON_CRAWL_TIMEOUT: int = 240
    # Maximum retry attempts for Common Crawl failures
    COMMON_CRAWL_MAX_RETRIES: int = 3
    # Default page limit for Common Crawl queries (prevents excessive data retrieval)
    COMMON_CRAWL_MAX_PAGES: int = 10000
    # Rate limit for Common Crawl API requests (requests per second)
    COMMON_CRAWL_RATE_LIMIT: float = 2.0
    
    # Archive Fallback Behavior
    # Delay between fallback attempts to different archive sources (seconds)
    ARCHIVE_FALLBACK_DELAY: int = 3
    # Fallback strategy: "sequential" (try sources in order) or "parallel" (try multiple simultaneously)
    ARCHIVE_FALLBACK_STRATEGY: str = "sequential"
    # Circuit breaker: number of consecutive failures before temporarily disabling source
    ARCHIVE_CIRCUIT_BREAKER_THRESHOLD: int = 5
    # Circuit breaker recovery time before re-enabling failed source (seconds)
    ARCHIVE_CIRCUIT_BREAKER_RECOVERY_TIME: int = 300
    
    # Archive Performance Settings
    # Cache TTL for archive query results to reduce redundant API calls (seconds)
    ARCHIVE_QUERY_CACHE_TTL: int = 3600  # 1 hour
    # Maximum concurrent requests to archive services (prevents overwhelming APIs)
    ARCHIVE_CONCURRENT_REQUESTS: int = 3
    # Batch size for bulk archive operations (optimizes API usage)
    ARCHIVE_BATCH_SIZE: int = 100
    # Global timeout for any archive operation regardless of source (seconds)
    ARCHIVE_GLOBAL_TIMEOUT: int = 300
    # Enable archive response compression to reduce bandwidth usage
    ARCHIVE_ENABLE_COMPRESSION: bool = True
    
    # ==========================================
    # DuckDB Analytics Engine Configuration
    # ==========================================
    
    # DuckDB Database Settings
    # Path to DuckDB database file (single-file architecture)
    DUCKDB_DATABASE_PATH: str = "/var/lib/duckdb/chrono_analytics.db"
    # Memory limit for DuckDB operations (string format: "4GB", "2048MB", etc.)
    DUCKDB_MEMORY_LIMIT: str = "4GB"
    # Number of worker threads for parallel processing
    DUCKDB_WORKER_THREADS: int = 4
    # Enable S3 extension for remote Parquet file access
    DUCKDB_ENABLE_S3: bool = False
    # Temporary directory for DuckDB operations
    DUCKDB_TEMP_DIRECTORY: str = "/tmp/duckdb"
    # Maximum memory percentage to use (60% leaves room for OS and other processes)
    DUCKDB_MAX_MEMORY_PERCENTAGE: int = 60
    
    # Parquet Configuration
    # Compression algorithm for Parquet files (ZSTD, GZIP, LZ4, SNAPPY)
    PARQUET_COMPRESSION: str = "ZSTD"
    # Row group size for optimal compression and query performance
    PARQUET_ROW_GROUP_SIZE: int = 1000000
    # Page size within row groups
    PARQUET_PAGE_SIZE: int = 1048576
    # Enable dictionary encoding for string columns
    PARQUET_ENABLE_DICTIONARY: bool = True
    
    # Data Synchronization Settings
    # Batch size for sync operations between PostgreSQL and DuckDB
    DATA_SYNC_BATCH_SIZE: int = 10000
    # Sync interval in seconds (300 = 5 minutes)
    DATA_SYNC_INTERVAL: int = 300
    # Enable dual-write mechanism (write to both PostgreSQL and DuckDB)
    ENABLE_DUAL_WRITE: bool = True
    # Number of retry attempts for failed sync operations
    SYNC_RETRY_ATTEMPTS: int = 3
    # Delay between sync retry attempts (seconds)
    SYNC_RETRY_DELAY: int = 60
    
    # Analytics Query Configuration
    # Default timeout for analytical queries (seconds)
    ANALYTICS_QUERY_TIMEOUT: int = 30
    # Cache TTL for analytics results (seconds)
    ANALYTICS_CACHE_TTL: int = 300
    ANALYTICS_LONG_CACHE_TTL: int = 1800  # For heavy queries
    # Maximum result size to prevent memory issues
    ANALYTICS_MAX_RESULT_SIZE: int = 1000000
    # Enable automatic query optimization and rewriting
    ENABLE_QUERY_OPTIMIZATION: bool = True
    
    # Analytics API Configuration
    ANALYTICS_MAX_QUERY_TIME: int = 30
    ANALYTICS_PAGINATION_SIZE: int = 1000
    ENABLE_ANALYTICS_WEBSOCKET: bool = True
    ANALYTICS_RATE_LIMIT: int = 100  # requests per minute
    ANALYTICS_EXPORT_TTL_HOURS: int = 48
    ANALYTICS_EXPORT_MAX_SIZE: int = 100000000  # 100MB
    TEMP_DIR: str = "/tmp"
    
    # Circuit Breaker Configuration for Analytics
    POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD: int = 5
    POSTGRESQL_CIRCUIT_BREAKER_TIMEOUT: int = 60
    DUCKDB_CIRCUIT_BREAKER_THRESHOLD: int = 3
    DUCKDB_CIRCUIT_BREAKER_TIMEOUT: int = 30
    
    # S3 Configuration (Optional - for remote Parquet storage)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None
    S3_PARQUET_PREFIX: str = "analytics/"
    
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
    
    # Parquet Pipeline Configuration
    PARQUET_STORAGE_PATH: str = "/data/parquet"
    PARQUET_COMPRESSION: str = "zstd"  # zstd, snappy, gzip, lz4
    PARQUET_COMPRESSION_LEVEL: int = 3
    PARQUET_ROW_GROUP_SIZE: int = 50_000_000  # 50MB target row groups
    PARQUET_PAGE_SIZE: int = 1_048_576  # 1MB page size
    PARQUET_USE_DICTIONARY: bool = True
    PARQUET_WRITE_STATISTICS: bool = True
    
    # Batch Processing Configuration
    BATCH_PROCESSING_ENABLED: bool = True
    DEFAULT_BATCH_SIZE: int = 50_000  # Default batch size for CDX processing
    CONTENT_BATCH_SIZE: int = 25_000  # Batch size for content analytics
    PROJECT_BATCH_SIZE: int = 10_000  # Batch size for project analytics
    MAX_CONCURRENT_BATCHES: int = 3   # Maximum concurrent batch operations
    BATCH_PROCESSING_INTERVAL_MINUTES: int = 30  # Auto-processing interval
    
    # Pipeline Performance Settings
    PIPELINE_MEMORY_LIMIT_GB: int = 2  # Memory limit for pipeline operations
    PIPELINE_TIMEOUT_MINUTES: int = 60  # Maximum processing time per batch
    ENABLE_PIPELINE_MONITORING: bool = True
    PARQUET_PARTITIONING_ENABLED: bool = True  # Enable date-based partitioning
    
    # DuckDB Analytics Configuration
    DUCKDB_ENABLED: bool = True
    DUCKDB_DATABASE_PATH: str = "/data/analytics.duckdb"
    DUCKDB_MEMORY_LIMIT: str = "2GB"
    DUCKDB_MAX_THREADS: int = 4
    
    # ==========================================
    # Data Synchronization Service Configuration
    # ==========================================
    
    # Core Data Sync Settings
    DATA_SYNC_ENABLED: bool = True
    DATA_SYNC_STRATEGY: str = "hybrid"  # real_time, near_real_time, batch, hybrid
    DATA_SYNC_BATCH_SIZE: int = 10000
    DATA_SYNC_RETRY_ATTEMPTS: int = 3
    DATA_SYNC_TIMEOUT: int = 300  # seconds
    DATA_SYNC_CONSISTENCY_LEVEL: str = "eventual"  # strong, eventual, weak
    
    # Dual-Write Configuration
    ENABLE_DUAL_WRITE: bool = True
    DUAL_WRITE_TIMEOUT: int = 30  # seconds
    DUAL_WRITE_RETRY_DELAY: int = 5  # seconds between retries
    DUAL_WRITE_MAX_RETRIES: int = 3
    
    # Circuit Breaker Settings
    POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD: int = 3
    POSTGRESQL_CIRCUIT_BREAKER_TIMEOUT: int = 30  # seconds
    DUCKDB_CIRCUIT_BREAKER_THRESHOLD: int = 5
    DUCKDB_CIRCUIT_BREAKER_TIMEOUT: int = 60  # seconds
    
    # Queue Management
    REAL_TIME_QUEUE_SIZE: int = 1000
    NEAR_REAL_TIME_QUEUE_SIZE: int = 10000
    BATCH_QUEUE_SIZE: int = 50000
    RECOVERY_QUEUE_SIZE: int = 5000
    DEAD_LETTER_QUEUE_SIZE: int = 1000
    
    # Performance Tuning
    MAX_CONCURRENT_SYNC_OPERATIONS: int = 10
    SYNC_WORKER_BATCH_SIZE: int = 100
    SYNC_WORKER_TIMEOUT: int = 300  # seconds
    SYNC_MONITORING_INTERVAL: int = 60  # seconds
    
    # ==========================================
    # Change Data Capture (CDC) Configuration
    # ==========================================
    
    # CDC Service Settings
    CDC_ENABLED: bool = True
    CDC_REPLICATION_SLOT_NAME: str = "chrono_scraper_cdc"
    CDC_PUBLICATION_NAME: str = "chrono_scraper_pub"
    
    # Monitored Tables (comma-separated list)
    CDC_MONITORED_TABLES: str = "users,projects,domains,pages_v2,project_pages,scrape_pages,scrape_sessions,api_configs"
    CDC_EXCLUDED_TABLES: str = "alembic_version,pg_stat_statements,audit_logs"
    
    # CDC Performance Settings
    CDC_MAX_BATCH_SIZE: int = 1000
    CDC_BATCH_TIMEOUT: int = 30  # seconds
    CDC_WAL_KEEP_SEGMENTS: int = 100
    CDC_MAX_REPLICATION_LAG_MINUTES: int = 5
    
    # Event Processing
    CDC_FILTER_SYSTEM_EVENTS: bool = True
    CDC_FILTER_UNCHANGED_UPDATES: bool = True
    CDC_MIN_EVENT_INTERVAL_SECONDS: int = 1
    
    # ==========================================
    # Data Consistency Validation Configuration
    # ==========================================
    
    # Consistency Check Settings
    CONSISTENCY_CHECK_ENABLED: bool = True
    CONSISTENCY_CHECK_INTERVAL_HOURS: int = 6  # Run every 6 hours
    CONSISTENCY_CHECK_SAMPLE_SIZE: int = 1000  # Records to sample for hash validation
    
    # Validation Types
    ENABLE_ROW_COUNT_VALIDATION: bool = True
    ENABLE_DATA_HASH_VALIDATION: bool = True
    ENABLE_BUSINESS_RULE_VALIDATION: bool = True
    ENABLE_REFERENTIAL_INTEGRITY_VALIDATION: bool = True
    
    # Conflict Resolution
    DEFAULT_CONFLICT_RESOLUTION_STRATEGY: str = "last_write_wins"  # last_write_wins, postgresql_wins, business_rules
    AUTO_RESOLVE_CONFLICTS: bool = True
    CONFLICT_RESOLUTION_TIMEOUT: int = 120  # seconds
    
    # Validation Performance
    VALIDATION_MAX_CONCURRENT_CHECKS: int = 5
    VALIDATION_TIMEOUT_PER_CHECK: int = 60  # seconds
    VALIDATION_HISTORY_RETENTION_DAYS: int = 30
    
    # ==========================================
    # Recovery and Resilience Configuration
    # ==========================================
    
    # Backup and Recovery
    ENABLE_AUTOMATIC_BACKUP: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_STORAGE_PATH: str = "/data/backups"
    BACKUP_COMPRESSION_ENABLED: bool = True
    
    # Disaster Recovery
    ENABLE_DISASTER_RECOVERY: bool = True
    DR_RECOVERY_POINT_OBJECTIVE_MINUTES: int = 60  # RPO: Max data loss
    DR_RECOVERY_TIME_OBJECTIVE_MINUTES: int = 30   # RTO: Max recovery time
    DR_BACKUP_VERIFICATION_ENABLED: bool = True
    
    # Health Monitoring
    HEALTH_CHECK_INTERVAL_SECONDS: int = 30
    HEALTH_CHECK_TIMEOUT_SECONDS: int = 10
    CRITICAL_ERROR_THRESHOLD: int = 5  # Consecutive failures before critical alert
    
    # Monitoring and Alerting
    ENABLE_SYNC_MONITORING: bool = True
    SYNC_LAG_ALERT_THRESHOLD_MINUTES: int = 15
    CONSISTENCY_SCORE_ALERT_THRESHOLD: float = 90.0  # Alert if below 90%
    DEAD_LETTER_QUEUE_ALERT_THRESHOLD: int = 100  # Alert if DLQ has >100 items
    
    # Webhook Notifications
    SYNC_ALERT_WEBHOOK_URL: Optional[str] = None
    CONSISTENCY_ALERT_WEBHOOK_URL: Optional[str] = None
    RECOVERY_ALERT_WEBHOOK_URL: Optional[str] = None
    
    # Email Notifications
    SYNC_ALERT_EMAIL: Optional[str] = None
    CRITICAL_ERROR_EMAIL: Optional[str] = None
    
    # ==========================================
    # Advanced Configuration Options
    # ==========================================
    
    # Memory Management
    SYNC_SERVICE_MEMORY_LIMIT_GB: int = 4
    CDC_SERVICE_MEMORY_LIMIT_GB: int = 2
    VALIDATION_SERVICE_MEMORY_LIMIT_GB: int = 1
    
    # Connection Pooling
    DUCKDB_CONNECTION_POOL_SIZE: int = 10
    DUCKDB_CONNECTION_TIMEOUT: int = 30  # seconds
    
    # Logging and Debugging
    SYNC_DEBUG_ENABLED: bool = False
    SYNC_LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    CDC_LOG_LEVEL: str = "INFO"
    VALIDATION_LOG_LEVEL: str = "INFO"
    
    # Feature Flags
    ENABLE_REAL_TIME_SYNC: bool = True
    ENABLE_NEAR_REAL_TIME_SYNC: bool = True
    ENABLE_BATCH_SYNC: bool = True
    ENABLE_RECOVERY_SYNC: bool = True
    ENABLE_CONFLICT_AUTO_RESOLUTION: bool = True
    ENABLE_ADVANCED_MONITORING: bool = True
    
    # Experimental Features
    ENABLE_PREDICTIVE_SYNC: bool = False  # AI-based sync optimization
    ENABLE_ADAPTIVE_BATCHING: bool = False  # Dynamic batch size adjustment
    ENABLE_MULTI_TENANT_ISOLATION: bool = False  # Tenant-specific sync strategies

    # ==========================================
    # Hybrid Query Router Configuration
    # ==========================================
    
    # Core Router Settings
    HYBRID_QUERY_ROUTER_ENABLED: bool = True
    HYBRID_ROUTER_DEFAULT_TIMEOUT: int = 300  # Default query timeout in seconds
    HYBRID_ROUTER_MAX_CONCURRENT_QUERIES: int = 100  # Maximum concurrent queries across all databases
    HYBRID_ROUTER_ENABLE_QUERY_CACHING: bool = True
    HYBRID_ROUTER_CACHE_DEFAULT_TTL: int = 1800  # Default cache TTL in seconds (30 minutes)
    HYBRID_ROUTER_ENABLE_QUERY_OPTIMIZATION: bool = True
    HYBRID_ROUTER_OPTIMIZATION_CACHE_SIZE: int = 10000  # Number of optimized queries to cache
    
    # Query Classification Settings
    HYBRID_ROUTER_AUTO_CLASSIFY_QUERIES: bool = True
    HYBRID_ROUTER_CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.7  # Minimum confidence for auto-routing
    HYBRID_ROUTER_ENABLE_QUERY_PATTERN_LEARNING: bool = True  # Learn from query execution patterns
    HYBRID_ROUTER_PATTERN_CACHE_SIZE: int = 50000  # Number of query patterns to cache
    
    # Database Routing Preferences
    HYBRID_ROUTER_OLTP_PREFERENCE: str = "postgresql"  # Primary OLTP database
    HYBRID_ROUTER_OLAP_PREFERENCE: str = "duckdb"     # Primary OLAP database
    HYBRID_ROUTER_ENABLE_CROSS_DATABASE_QUERIES: bool = True  # Enable hybrid queries
    HYBRID_ROUTER_LARGE_RESULT_THRESHOLD: int = 100000  # Rows threshold for routing to analytics DB
    HYBRID_ROUTER_LONG_QUERY_THRESHOLD: float = 5.0  # Seconds threshold for routing to analytics DB
    
    # Connection Pool Configuration
    HYBRID_ROUTER_POSTGRESQL_POOL_SIZE: int = 20
    HYBRID_ROUTER_POSTGRESQL_MAX_OVERFLOW: int = 40
    HYBRID_ROUTER_DUCKDB_POOL_SIZE: int = 10
    HYBRID_ROUTER_DUCKDB_MAX_OVERFLOW: int = 20
    HYBRID_ROUTER_CONNECTION_TIMEOUT: int = 30  # Connection acquisition timeout
    HYBRID_ROUTER_CONNECTION_IDLE_TIMEOUT: int = 300  # Idle connection timeout
    HYBRID_ROUTER_CONNECTION_MAX_LIFETIME: int = 3600  # Maximum connection lifetime
    
    # Circuit Breaker Configuration
    HYBRID_ROUTER_CIRCUIT_BREAKER_ENABLED: bool = True
    POSTGRESQL_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    POSTGRESQL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 60  # Seconds
    DUCKDB_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    DUCKDB_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30  # Seconds
    HYBRID_ROUTER_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = 3
    
    # Performance Optimization Settings
    HYBRID_ROUTER_ENABLE_QUERY_REWRITING: bool = True
    HYBRID_ROUTER_ENABLE_PREDICATE_PUSHDOWN: bool = True
    HYBRID_ROUTER_ENABLE_JOIN_OPTIMIZATION: bool = True
    HYBRID_ROUTER_ENABLE_INDEX_HINTS: bool = True
    HYBRID_ROUTER_MAX_OPTIMIZATION_TIME: float = 2.0  # Maximum time to spend on query optimization
    HYBRID_ROUTER_OPTIMIZATION_STRATEGIES_LIMIT: int = 5  # Maximum optimization strategies to apply
    
    # Resource Management
    HYBRID_ROUTER_ENABLE_RESOURCE_THROTTLING: bool = True
    HYBRID_ROUTER_MAX_CPU_PERCENT: float = 80.0
    HYBRID_ROUTER_MAX_MEMORY_MB: float = 8192.0  # 8GB
    HYBRID_ROUTER_MAX_CONNECTIONS_GLOBAL: int = 200
    HYBRID_ROUTER_QUERY_MEMORY_LIMIT_MB: int = 1024  # Per-query memory limit
    HYBRID_ROUTER_ENABLE_ADAPTIVE_THROTTLING: bool = True  # Adjust throttling based on system load
    
    # Query Priority Configuration
    HYBRID_ROUTER_ENABLE_QUERY_PRIORITIZATION: bool = True
    HYBRID_ROUTER_CRITICAL_PRIORITY_MAX_CONCURRENT: int = 10
    HYBRID_ROUTER_HIGH_PRIORITY_MAX_CONCURRENT: int = 30
    HYBRID_ROUTER_NORMAL_PRIORITY_MAX_CONCURRENT: int = 80
    HYBRID_ROUTER_LOW_PRIORITY_MAX_CONCURRENT: int = 50
    HYBRID_ROUTER_BACKGROUND_PRIORITY_MAX_CONCURRENT: int = 20
    
    # Caching Configuration
    HYBRID_ROUTER_CACHE_REDIS_URL: Optional[str] = None  # Uses REDIS_URL if not specified
    HYBRID_ROUTER_ENABLE_LOCAL_CACHE: bool = True
    HYBRID_ROUTER_LOCAL_CACHE_SIZE: int = 1000  # Number of entries in local cache
    HYBRID_ROUTER_LOCAL_CACHE_TTL: int = 300  # Local cache TTL in seconds
    HYBRID_ROUTER_CACHE_ANALYTICS_QUERIES: bool = True
    HYBRID_ROUTER_CACHE_OLTP_QUERIES: bool = False  # Don't cache transactional queries
    
    # Monitoring and Observability
    HYBRID_ROUTER_ENABLE_MONITORING: bool = True
    HYBRID_ROUTER_METRICS_COLLECTION_INTERVAL: int = 60  # Collect metrics every 60 seconds
    HYBRID_ROUTER_PERFORMANCE_SNAPSHOT_INTERVAL: int = 300  # Performance snapshots every 5 minutes
    HYBRID_ROUTER_ENABLE_PROMETHEUS_METRICS: bool = True
    ENABLE_PROMETHEUS_METRICS: bool = True  # Global Prometheus enablement
    HYBRID_ROUTER_PROMETHEUS_PORT: int = 9090
    HYBRID_ROUTER_METRICS_RETENTION_DAYS: int = 30
    
    # Alerting Configuration
    HYBRID_ROUTER_ENABLE_ALERTING: bool = True
    HYBRID_ROUTER_ALERT_CHECK_INTERVAL: int = 30  # Check alerts every 30 seconds
    HYBRID_ROUTER_HIGH_ERROR_RATE_THRESHOLD: float = 5.0  # Percentage
    HYBRID_ROUTER_SLOW_QUERY_THRESHOLD: float = 2.0  # Seconds
    HYBRID_ROUTER_LOW_CACHE_HIT_RATE_THRESHOLD: float = 50.0  # Percentage
    HYBRID_ROUTER_WEBHOOK_URL: Optional[str] = None  # Webhook for alert notifications
    HYBRID_ROUTER_ALERT_EMAIL: Optional[str] = None  # Email for alert notifications
    
    # Query Analysis Configuration
    HYBRID_ROUTER_ENABLE_QUERY_ANALYSIS: bool = True
    HYBRID_ROUTER_ANALYSIS_CACHE_SIZE: int = 10000
    HYBRID_ROUTER_ANALYSIS_CACHE_TTL: int = 1800  # 30 minutes
    HYBRID_ROUTER_ENABLE_SQL_PARSING: bool = True  # Enable advanced SQL parsing (requires sqlparse)
    HYBRID_ROUTER_ENABLE_TABLE_STATISTICS: bool = True  # Collect and use table statistics
    HYBRID_ROUTER_TABLE_STATS_REFRESH_INTERVAL: int = 3600  # Refresh table stats every hour
    
    # Backup and Recovery Integration
    HYBRID_ROUTER_ENABLE_BACKUP_COORDINATION: bool = True
    HYBRID_ROUTER_BACKUP_PAUSE_QUERIES: bool = False  # Pause queries during backup
    HYBRID_ROUTER_BACKUP_PRIORITY_QUERIES_ONLY: bool = True  # Allow only critical queries during backup
    
    # Security and Access Control
    HYBRID_ROUTER_ENABLE_QUERY_AUDITING: bool = True
    HYBRID_ROUTER_AUDIT_ALL_QUERIES: bool = False  # Audit only failed/slow queries by default
    HYBRID_ROUTER_AUDIT_SLOW_QUERY_THRESHOLD: float = 5.0  # Audit queries slower than 5 seconds
    HYBRID_ROUTER_ENABLE_QUERY_SANITIZATION: bool = True  # Sanitize queries before logging
    HYBRID_ROUTER_MAX_QUERY_LOG_LENGTH: int = 1000  # Maximum query length in logs
    
    # Development and Debug Settings
    HYBRID_ROUTER_DEBUG_MODE: bool = False
    HYBRID_ROUTER_LOG_ALL_QUERIES: bool = False  # Log all queries (performance impact)
    HYBRID_ROUTER_LOG_ROUTING_DECISIONS: bool = True  # Log routing decisions
    HYBRID_ROUTER_LOG_OPTIMIZATION_RESULTS: bool = True  # Log query optimizations
    HYBRID_ROUTER_ENABLE_QUERY_EXPLAIN: bool = True  # Enable query plan explanation
    
    # Feature Flags
    HYBRID_ROUTER_ENABLE_EXPERIMENTAL_FEATURES: bool = False
    HYBRID_ROUTER_ENABLE_MACHINE_LEARNING_ROUTING: bool = False  # ML-based routing (future)
    HYBRID_ROUTER_ENABLE_PREDICTIVE_CACHING: bool = False  # Predictive cache preloading
    HYBRID_ROUTER_ENABLE_AUTO_SCALING: bool = False  # Automatic resource scaling
    
    # API Configuration
    HYBRID_ROUTER_API_ENABLE_ADMIN_ENDPOINTS: bool = True
    HYBRID_ROUTER_API_REQUIRE_ADMIN_AUTH: bool = True  # Require admin auth for management endpoints
    HYBRID_ROUTER_API_RATE_LIMIT: int = 1000  # API requests per hour per user
    HYBRID_ROUTER_API_MAX_QUERY_SIZE: int = 1048576  # Maximum query size (1MB)
    
    @property
    def HYBRID_ROUTER_REDIS_URL(self) -> str:
        """Get Redis URL for hybrid router (uses main Redis if not specified)"""
        return self.HYBRID_ROUTER_CACHE_REDIS_URL or self.REDIS_URL


settings = Settings()