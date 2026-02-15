from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    published_date: str | None = None
    engines: list[str] | None = None
    score: float | None = None
    category: str | None = None


class SearchProvider(Protocol):
    name: str
    cost_per_query: float
    reliability: float
    freshness: float

    def enabled(self) -> bool: ...

    def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...
