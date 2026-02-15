from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ...config import Settings
from .base import SearchProvider, SearchResult
from .paid import StubPaidProvider
from .searxng import SearXNGProvider


@dataclass
class BudgetState:
    day: dt.date = field(default_factory=dt.date.today)
    month: tuple[int, int] = field(default_factory=lambda: (dt.date.today().year, dt.date.today().month))
    daily_queries: int = 0
    monthly_spend: float = 0.0

    def refresh(self) -> None:
        today = dt.date.today()
        if today != self.day:
            self.day = today
            self.daily_queries = 0

        month_key = (today.year, today.month)
        if month_key != self.month:
            self.month = month_key
            self.monthly_spend = 0.0


class SourceRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = BudgetState()
        self.providers: list[SearchProvider] = [
            SearXNGProvider(base_url=settings.searxng_base_url, engines=settings.searxng_engines),
            StubPaidProvider("brave", settings.brave_api_key, 0.003, 0.84, 0.84),
            StubPaidProvider("serpapi", settings.serpapi_api_key, 0.01, 0.9, 0.88),
            StubPaidProvider("google_cse", settings.google_cse_api_key, 0.005, 0.85, 0.85),
            StubPaidProvider("dataforseo", settings.dataforseo_login, 0.015, 0.86, 0.9),
            StubPaidProvider("opencorporates", settings.opencorporates_api_key, 0.002, 0.8, 0.65),
        ]

    def _budget_available(self, provider: SearchProvider) -> bool:
        self.state.refresh()
        if self.state.daily_queries >= self.settings.daily_query_budget:
            return False
        if self.state.monthly_spend + provider.cost_per_query > self.settings.monthly_spend_limit_usd:
            return False
        return True

    def _rank_providers(self) -> list[SearchProvider]:
        enabled = [p for p in self.providers if p.enabled()]

        # Lower score wins: cheap providers with high quality get prioritized.
        def score(p: SearchProvider) -> float:
            quality = max(0.01, p.reliability * 0.6 + p.freshness * 0.4)
            return p.cost_per_query / quality

        return sorted(enabled, key=score)

    def search(self, query: str, limit: int = 5) -> tuple[str, list[SearchResult]]:
        for provider in self._rank_providers():
            if not self._budget_available(provider):
                continue
            results = provider.search(query=query, limit=limit)
            if results:
                self.state.daily_queries += 1
                self.state.monthly_spend += provider.cost_per_query
                return provider.name, results
        return "none", []

    def budget_snapshot(self) -> dict[str, float | int]:
        self.state.refresh()
        return {
            "daily_queries": self.state.daily_queries,
            "daily_limit": self.settings.daily_query_budget,
            "monthly_spend": round(self.state.monthly_spend, 4),
            "monthly_limit": self.settings.monthly_spend_limit_usd,
        }
