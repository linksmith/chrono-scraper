"""
Application configuration using Pydantic Settings
"""
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
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
    
    # User registration
    USERS_OPEN_REGISTRATION: bool = True
    REQUIRE_EMAIL_VERIFICATION: bool = True
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

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
    MEILISEARCH_MASTER_KEY: str = "masterKey"
    
    # Email
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None
    
    # Superuser
    FIRST_SUPERUSER: str = "admin@chrono-scraper.com"
    FIRST_SUPERUSER_PASSWORD: str = "changeme"
    
    # Firecrawl
    FIRECRAWL_API_KEY: Optional[str] = None
    FIRECRAWL_API_URL: str = "https://api.firecrawl.dev"
    
    # Proxy settings
    USE_PROXY: bool = False
    PROXY_URL: Optional[str] = None
    PROXY_USERNAME: Optional[str] = None
    PROXY_PASSWORD: Optional[str] = None
    PROXY_ENDPOINT: Optional[str] = None
    PROXY_PORT_RESIDENTIAL: Optional[int] = None
    PROXY_PORT_DATACENTER: Optional[int] = None
    
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
    
    # OAuth2 settings
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    OAUTH2_ENABLED: bool = False


settings = Settings()