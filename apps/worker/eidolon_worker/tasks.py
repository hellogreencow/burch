from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from .config import Settings

DISCOVERY_QUERIES = [
    "emerging consumer brand instagram growth",
    "new wellness brand tiktok viral",
    "founder-led food brand expansion",
    "consumer d2c brand retail expansion",
]


def refresh_snapshot(settings: Settings) -> tuple[bool, str]:
    url = f"{settings.api_base_url.rstrip('/')}/v1/admin/refresh"
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(url)
        res.raise_for_status()
        return True, "snapshot refreshed"
    except Exception as exc:
        return False, f"refresh failed: {exc}"


def discover_candidates(settings: Settings, limit: int = 8) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []

    with httpx.Client(timeout=15.0) as client:
        for query in DISCOVERY_QUERIES:
            try:
                res = client.get(
                    f"{settings.searxng_base_url.rstrip('/')}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "safesearch": 0,
                        "pageno": 1,
                        "engines": settings.searxng_engines,
                    },
                )
                res.raise_for_status()
                payload = res.json()
            except Exception:
                continue

            for row in payload.get("results", [])[:limit]:
                discovered.append(
                    {
                        "query": query,
                        "title": row.get("title", ""),
                        "url": row.get("url", ""),
                        "snippet": row.get("content", ""),
                        "engine": row.get("engine", "searxng"),
                        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                    }
                )
    return discovered
