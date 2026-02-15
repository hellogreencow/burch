from __future__ import annotations

from dataclasses import dataclass

import httpx

from .base import SearchResult


@dataclass
class SearXNGProvider:
    base_url: str
    engines: str = ""
    name: str = "searxng"
    cost_per_query: float = 0.0
    reliability: float = 0.62
    freshness: float = 0.7

    def enabled(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.enabled():
            return []

        url = f"{self.base_url.rstrip('/')}/search"
        base_params = {
            "q": query,
            "format": "json",
            "pageno": 1,
            "safesearch": 0,
        }

        def _fetch(params: dict) -> dict:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, params=params)
            res.raise_for_status()
            return res.json()

        try:
            params = dict(base_params)
            if self.engines:
                params["engines"] = self.engines
            payload = _fetch(params)
            # Some engines get rate-limited/captcha'd intermittently. If that happens, retry once without an explicit
            # engine restriction so SearXNG can use whatever engines are currently healthy.
            if self.engines and not (payload.get("results") or []):
                payload = _fetch(dict(base_params))
        except Exception:
            return []

        results = []
        for row in payload.get("results", [])[:limit]:
            results.append(
                SearchResult(
                    title=row.get("title", "Untitled"),
                    url=row.get("url", ""),
                    snippet=row.get("content", ""),
                    source=row.get("engine", "searxng"),
                    published_date=row.get("publishedDate"),
                    engines=row.get("engines"),
                    score=row.get("score"),
                    category=row.get("category"),
                )
            )
        return results
