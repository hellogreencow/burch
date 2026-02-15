from __future__ import annotations

from dataclasses import dataclass

from .base import SearchResult


@dataclass
class StubPaidProvider:
    name: str
    api_key: str
    cost_per_query: float
    reliability: float
    freshness: float

    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        # Placeholder adapter. Integrate concrete API calls as keys/providers are activated.
        _ = (query, limit)
        return []
