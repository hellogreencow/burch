from __future__ import annotations

import re


_TRAILING_VERSION_RE = re.compile(r"\s+\d+$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Common boilerplate tokens that show up in titles/snippets and create duplicate entities.
_DROP_TOKENS = {
    "the",
    "official",
    "site",
    "store",
    "shop",
    "online",
    "brand",
    "inc",
    "llc",
    "ltd",
    "co",
    "company",
    "corp",
    "corporation",
}


def canonical_display_name(name: str) -> str:
    """Human-facing cleanup (keeps punctuation, mainly normalizes whitespace)."""
    normalized = " ".join((name or "").split()).strip()
    canonical = _TRAILING_VERSION_RE.sub("", normalized)
    return canonical or normalized


def entity_key_from_name(name: str) -> str:
    """
    Stable, aggressive normalization for de-duplicating near-identical brand rows.
    Intended for internal grouping only (not for display).
    """
    cleaned = canonical_display_name(name).lower()
    # Drop common trademark glyphs and similar punctuation noise.
    cleaned = cleaned.replace("™", "").replace("®", "")
    cleaned = _NON_ALNUM_RE.sub(" ", cleaned)
    tokens = [t for t in cleaned.split() if t and t not in _DROP_TOKENS]
    return " ".join(tokens)[:140].strip()

