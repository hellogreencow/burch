from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    app_name: str = "BURCH-EIDOLON API"
    cors_origin: str = "http://localhost:3000"

    database_url: str = "sqlite+pysqlite:///./eidolon.db"
    redis_url: str = "redis://localhost:6379/0"

    searxng_base_url: str = "http://localhost:8080"
    # Restrict to engines that reliably return results without CAPTCHAs in a self-hosted setup.
    # Comma-separated list passed through to SearXNG's `engines` query param.
    searxng_engines: str = "duckduckgo,brave,seznam,bing"
    daily_query_budget: int = 500
    monthly_spend_limit_usd: float = 300.0

    brave_api_key: str = ""
    serpapi_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    opencorporates_api_key: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_fast_model: str = "meta-llama/llama-3.1-8b-instruct"
    openrouter_strong_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_max_input_tokens: int = Field(default=12000, ge=512, le=32000)
    openrouter_max_output_tokens: int = Field(default=1200, ge=128, le=8192)

    reports_dir: str = "./reports/generated"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
