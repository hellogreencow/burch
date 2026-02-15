from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    api_base_url: str = "http://api:8000"
    searxng_base_url: str = "http://searxng:8080"
    # Comma-separated SearXNG engines to use (avoid captcha-prone defaults).
    searxng_engines: str = "mojeek,bing"
    worker_interval_seconds: int = 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
