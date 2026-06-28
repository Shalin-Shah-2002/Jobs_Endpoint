from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JOBS_",
        extra="ignore",
    )

    app_name: str = "Jobs Endpoint"
    api_key: str = Field(default="dev-api-key", min_length=8)
    database_url: str = "sqlite:///./jobs.db"
    enable_mock_source: bool = True
    read_rate_limit: int = Field(default=120, ge=1, le=10_000)
    write_rate_limit: int = Field(default=10, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()

