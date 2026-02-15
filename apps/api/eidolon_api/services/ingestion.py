from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from .. import models
from .entity import entity_key_from_name
from .providers.router import SourceRouter
from .scoring import AOV_BY_CATEGORY


UNIVERSE_QUERY_LANES: list[tuple[str, str]] = [
    # These are tuned to bias towards official brand sites / commerce pages, not publisher listicles.
    ("outdoor apparel brand shop official site", "Outdoor"),
    ("trail running brand shop official site", "Outdoor"),
    ("skincare brand shop official site", "Beauty"),
    ("haircare brand shop official site", "Beauty"),
    ("clean personal care brand shop official site", "Personal Care"),
    ("functional beverage brand shop direct to consumer", "Food & Beverage"),
    ("snack brand shop direct to consumer", "Food & Beverage"),
    ("wellness supplement brand shop official site", "Wellness"),
    ("pet food brand shop direct to consumer", "Pet"),
    ("home fragrance brand shop official site", "Home Goods"),
    ("home goods brand shop official site", "Home Goods"),
    ("baby brand shop direct to consumer", "Childcare"),
    ("kids toy brand shop direct to consumer", "Childcare"),
    ("consumer electronics brand shop direct to consumer", "Consumer Tech"),
    ("apparel brand shop direct to consumer", "Apparel"),
]

EXCLUDED_HOST_FRAGMENTS = (
    "wikipedia.org",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "pinterest.com",
    "amazon.",
    "etsy.com",
    "ebay.",
)

# This is intentionally conservative: we only use this list to avoid treating publishers as brands.
PUBLISHER_HOST_FRAGMENTS = (
    "cambridge.org",
    "merriam-webster.com",
    "dictionary.com",
    "britannica.com",
    "wiktionary.org",
    "trendhunter.com",
    "sgbonline.com",
    "sgbmedia.com",
    "powerbrands.com",
    "forbes.com",
    "techcrunch.com",
    "nytimes.com",
    "wsj.com",
    "bloomberg.com",
    "fortune.com",
    "businessinsider.com",
    "theverge.com",
    "axios.com",
    "medium.com",
    "substack.com",
    "gq.com",
    "esquire.com",
    "highsnobiety.com",
    "outsideonline.com",
    "carryology.com",
    "treelinereview.com",
    "outdoortechlab.com",
    "tastingtable.com",
    "thebump.com",
    "allrecipes.com",
    "seriouseats.com",
    "foodandwine.com",
)

MOMENTUM_TERMS = {
    "growth",
    "surge",
    "expansion",
    "viral",
    "launch",
    "opening",
    "scale",
    "scaled",
    "momentum",
    "raised",
    "seed",
    "series",
    "sold out",
}

RISK_TERMS = {
    "lawsuit",
    "recall",
    "decline",
    "bankrupt",
    "shutdown",
    "layoff",
    "controversy",
    "investigation",
    "ban",
    "fraud",
    "warning",
}


def _deal_structure(heat: float, risk: float, asymmetry: float, capital: float) -> str:
    if asymmetry > 78 and risk < 55 and capital < 30:
        return "Minority growth investment"
    if asymmetry > 80 and risk < 65 and capital >= 30:
        return "Debt plus earnout"
    if heat > 82 and risk <= 60:
        return "IP partnership"
    if risk > 70:
        return "Licensing structure"
    return "Control acquisition"


def _monday_of_week(today: dt.date | None = None) -> dt.date:
    base = today or dt.date.today()
    return base - dt.timedelta(days=base.weekday())


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _host(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # Common ecommerce subdomains that should collapse into the canonical brand host.
    for prefix in ("shop.", "store."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _is_excluded_host(host: str) -> bool:
    lowered = host.lower()
    if any(fragment in lowered for fragment in EXCLUDED_HOST_FRAGMENTS):
        return True
    return False


def _is_publisher_host(host: str) -> bool:
    lowered = host.lower()
    return any(fragment in lowered for fragment in PUBLISHER_HOST_FRAGMENTS)


def _canonical_site_url(host: str) -> str:
    # Prefer https; we will follow redirects when fetching metadata.
    return f"https://{host}/"


def _stable_brand_id(host: str) -> str:
    digest = hashlib.sha1(host.encode("utf-8")).hexdigest()[:12]
    return f"brand-{digest}"


TITLE_SPLIT_RE = re.compile(r"\s[-|:]\s")


def _name_from_title_tag(title: str) -> str:
    cleaned = _clean_text(title)
    if not cleaned:
        return ""
    head = TITLE_SPLIT_RE.split(cleaned)[0].strip()
    head = re.sub(r"\s+(official site|official store|shop online|store)\s*$", "", head, flags=re.I).strip()
    return head[:80]


def _domain_label(host: str) -> str:
    core = host.split(":", 1)[0]
    core = core.split(".")
    core = [p for p in core if p and p not in {"www"}]
    if not core:
        return ""
    # naive: use second-level label (works for .com; good enough for PoC)
    if len(core) >= 2:
        label = core[-2]
    else:
        label = core[0]
    label = re.sub(r"[^a-z0-9]+", " ", label, flags=re.I).strip()
    return label


def _title_case_words(value: str) -> str:
    words = [w for w in re.split(r"\s+", value.strip()) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _fallback_brand_name(host: str) -> str:
    return _title_case_words(_domain_label(host)) or host


def _extract_title_and_description(html: str) -> tuple[str, str]:
    # Keep parsing lightweight: regex is sufficient for a title + meta description best-effort.
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title = _clean_text(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else ""
    desc_match = re.search(
        r'<meta[^>]+name=[\"\']description[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']',
        html,
        flags=re.I,
    )
    desc = _clean_text(desc_match.group(1)) if desc_match else ""
    return title, desc


def _fetch_site_metadata(site_url: str) -> tuple[str, str, str]:
    try:
        with httpx.Client(timeout=7.0, follow_redirects=True, headers={"User-Agent": "BURCH-EIDOLON/1.0"}) as client:
            res = client.get(site_url)
            res.raise_for_status()
            html = res.text
    except Exception:
        return site_url, "", ""

    title, desc = _extract_title_and_description(html)
    return str(res.url), title, desc


def _looks_like_publisher(title: str, desc: str) -> bool:
    text = f"{title} {desc}".lower()
    publisher_terms = (
        "recipes",
        "recipe",
        "news",
        "magazine",
        "blog",
        "reviews",
        "review",
        "editorial",
        "podcast",
        "dictionary",
        "definition",
        "meaning",
        "encyclopedia",
        "wiki",
        "press",
        "journal",
    )
    ecommerce_terms = ("shop", "store", "buy", "cart", "checkout", "subscribe")
    if any(term in text for term in publisher_terms) and not any(term in text for term in ecommerce_terms):
        return True
    return False


def _try_shopify_products(site_url: str) -> tuple[int | None, float | None]:
    # Best-effort: Shopify commonly exposes /products.json
    base = site_url.rstrip("/")
    url = f"{base}/products.json?limit=250&page=1"
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers={"User-Agent": "BURCH-EIDOLON/1.0"}) as client:
            res = client.get(url)
            if res.status_code != 200:
                return None, None
            payload = res.json()
    except Exception:
        return None, None

    products = payload.get("products")
    if not isinstance(products, list) or not products:
        return 0, None

    prices: list[float] = []
    for product in products:
        variants = product.get("variants") if isinstance(product, dict) else None
        if not isinstance(variants, list):
            continue
        for v in variants:
            if not isinstance(v, dict):
                continue
            price_raw = v.get("price")
            try:
                price = float(price_raw)
            except Exception:
                continue
            if price > 0:
                prices.append(price)

    prices.sort()
    median_price = prices[len(prices) // 2] if prices else None
    return len(products), median_price


def _count_term_hits(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    hits = 0
    for term in terms:
        if term in lowered:
            hits += 1
    return hits


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _source_reliability(source: str) -> float:
    s = (source or "").lower()
    if "google" in s or "startpage" in s:
        return 0.72
    if "duckduckgo" in s:
        return 0.64
    if "bing" in s:
        return 0.66
    if "reddit" in s:
        return 0.72
    if "news" in s:
        return 0.78
    return 0.62


@dataclass
class CandidateAggregate:
    host: str
    categories: dict[str, int] = field(default_factory=dict)
    appearances: int = 0
    visibility: float = 0.0
    engines: set[str] = field(default_factory=set)
    momentum_hits: int = 0
    risk_hits: int = 0
    seed_evidence: list[dict[str, str]] = field(default_factory=list)

    def bump_category(self, category: str) -> None:
        self.categories[category] = self.categories.get(category, 0) + 1

    @property
    def primary_category(self) -> str:
        if not self.categories:
            return "Unknown"
        return max(self.categories.items(), key=lambda item: item[1])[0]


def _collect_universe_candidates(router: SourceRouter) -> dict[str, CandidateAggregate]:
    candidates: dict[str, CandidateAggregate] = {}

    for query, category in UNIVERSE_QUERY_LANES:
        provider, results = router.search(query=query, limit=25)
        _ = provider
        for r in results:
            host = _host(r.url)
            if not host:
                continue
            if _is_excluded_host(host) or _is_publisher_host(host):
                continue

            agg = candidates.get(host)
            if not agg:
                agg = CandidateAggregate(host=host)
                candidates[host] = agg

            agg.appearances += 1
            agg.bump_category(category)
            agg.engines.add((r.source or "searxng").lower())
            agg.visibility += float(r.score or 1.0)
            text = f"{r.title} {r.snippet}"
            agg.momentum_hits += _count_term_hits(text, MOMENTUM_TERMS)
            agg.risk_hits += _count_term_hits(text, RISK_TERMS)
            if len(agg.seed_evidence) < 6:
                agg.seed_evidence.append(
                    {
                        "title": _clean_text(r.title)[:240],
                        "url": _clean_text(r.url)[:500],
                        "snippet": _clean_text(r.snippet)[:600],
                        "source": _clean_text(r.source)[:120],
                    }
                )

    return candidates


def _rank_candidates(candidates: Iterable[CandidateAggregate]) -> list[CandidateAggregate]:
    ranked: list[tuple[float, CandidateAggregate]] = []
    for agg in candidates:
        appearances = float(agg.appearances)
        engines = float(len(agg.engines))
        momentum = float(agg.momentum_hits)
        visibility = float(agg.visibility)
        risk = float(agg.risk_hits)
        # Composite prioritizes acceleration keywords + repeated appearance across lanes.
        score = appearances * 6.0 + engines * 4.0 + momentum * 5.0 + visibility * 0.6 - risk * 8.0
        ranked.append((score, agg))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [agg for _, agg in ranked]


def _signal_counts_from_results(results: list[dict[str, str]], brand_host: str) -> dict[str, int]:
    counts = {
        "brand_site": 0,
        "instagram": 0,
        "tiktok": 0,
        "reddit": 0,
        "pinterest": 0,
        "substack": 0,
        "medium": 0,
        "youtube": 0,
        "meta_ads": 0,
        "jobs": 0,
        "stockists": 0,
        "resale": 0,
    }

    resale_hosts = ("depop.com", "poshmark.com", "grailed.com", "ebay.", "stockx.com")
    job_hosts = ("greenhouse.io", "lever.co", "workable.com", "ashbyhq.com")

    for row in results:
        url = row.get("url", "")
        host = _host(url)
        title = (row.get("title", "") or "").lower()
        snippet = (row.get("snippet", "") or "").lower()
        text = f"{title} {snippet}"

        if host == brand_host or host.endswith(f".{brand_host}"):
            counts["brand_site"] += 1
        if "instagram.com" in host:
            counts["instagram"] += 1
        if "tiktok.com" in host:
            counts["tiktok"] += 1
        if "reddit.com" in host:
            counts["reddit"] += 1
        if "pinterest.com" in host:
            counts["pinterest"] += 1
        if "substack.com" in host:
            counts["substack"] += 1
        if "medium.com" in host:
            counts["medium"] += 1
        if "youtube.com" in host or "youtu.be" in host:
            counts["youtube"] += 1
        if "facebook.com" in host and "ads/library" in url:
            counts["meta_ads"] += 1
        if any(h in host for h in job_hosts) or "linkedin.com" in host:
            if "job" in text or "careers" in text or "hiring" in text:
                counts["jobs"] += 1
        if "stockist" in text or "stockists" in text or "where to buy" in text:
            counts["stockists"] += 1
        if any(h in host for h in resale_hosts) or "resale" in text:
            counts["resale"] += 1

    return counts


def _compute_snapshot_metrics(
    *,
    category: str,
    evidence_results: list[dict[str, str]],
    traffic_results: list[dict[str, str]],
    brand_host: str,
    sku_count: int | None,
    median_price_usd: float | None,
) -> dict[str, float]:
    # Signals come only from retrieved evidence (no randomness).
    term_blob = " ".join(f"{r.get('title','')} {r.get('snippet','')}" for r in evidence_results)
    momentum_hits = float(_count_term_hits(term_blob, MOMENTUM_TERMS))
    risk_hits = float(_count_term_hits(term_blob, RISK_TERMS))

    signals = _signal_counts_from_results(evidence_results, brand_host=brand_host)
    traffic_signals = _signal_counts_from_results(traffic_results, brand_host=brand_host)

    instagram = signals["instagram"]
    tiktok = signals["tiktok"]
    reddit = signals["reddit"]
    pinterest = signals["pinterest"]
    blogs = signals["substack"] + signals["medium"]
    resale = signals["resale"]

    indexed_pages = max(1, traffic_signals["brand_site"])
    traffic_k = _clamp(8 + indexed_pages * 10 + momentum_hits * 4 + (instagram + tiktok) * 6, 5, 450)

    sku_proxy = float(sku_count) if sku_count is not None else _clamp(indexed_pages * 6, 10, 600)
    sku_proxy = _clamp(sku_proxy, 1, 2000)

    engagement_quality = _clamp(0.62 + (instagram + tiktok) / 40 - risk_hits / 18, 0.2, 0.98)
    engagement_rate = _clamp(1.0 + (instagram + tiktok) * 0.8 + momentum_hits * 0.6, 0.5, 18.0)
    comments_to_likes = _clamp(0.04 + engagement_quality * 0.11, 0.02, 0.32)
    repeat_density = _clamp(0.12 + engagement_quality * 0.55 - risk_hits * 0.01, 0.08, 0.95)
    influencer_overlap = _clamp(22 + (instagram + tiktok) * 4 + momentum_hits * 3, 5, 99)
    ugc_reposts = _clamp(6 + (instagram + tiktok) * 3 + pinterest * 1.5, 1, 95)

    meta_ads = _clamp(10 + signals["meta_ads"] * 18 + momentum_hits * 2, 0, 99)
    hiring = _clamp(signals["jobs"] * 8 + momentum_hits * 2, 0, 55)
    stockists = _clamp(signals["stockists"] * 8 + momentum_hits * 1.2, 0, 45)
    sellout = _clamp(35 + momentum_hits * 4 + (instagram + tiktok) * 2 - risk_hits * 3, 5, 99)

    google_trends = _clamp(18 + (instagram + tiktok) * 4 + momentum_hits * 6 - risk_hits * 3, 2, 100)
    reddit_mentions = _clamp(reddit * 12 + momentum_hits * 3, 0, 120)
    pinterest_saves = _clamp(pinterest * 10 + momentum_hits * 2, 0, 100)
    blog_mentions = _clamp(blogs * 8 + momentum_hits * 1.5, 0, 40)
    resale_activity = _clamp(resale * 12 + momentum_hits * 1.2, 0, 100)

    # AOV: if we can observe a median item price, use it directionally; otherwise category default.
    aov = float(median_price_usd) if median_price_usd else float(AOV_BY_CATEGORY.get(category, 60.0))
    aov = _clamp(aov * 1.15, 10, 400)

    # Revenue (annual, $M) from proxy traffic + conversion + AOV.
    conversion_pct = _clamp(0.9 + (instagram + tiktok) / 50 + engagement_quality * 0.9 - risk_hits / 22, 0.7, 5.5)
    monthly_rev = (traffic_k * 1000) * (conversion_pct / 100.0) * aov
    annual_rev_musd = _clamp(monthly_rev * 12 / 1_000_000, 0.4, 350.0)
    rev_p10 = _clamp(annual_rev_musd * 0.72, 0.2, 350.0)
    rev_p90 = _clamp(annual_rev_musd * 1.32, 0.3, 600.0)

    # Capital intensity: category prior with small adjustment for SKU complexity.
    base_capital = {
        "Food & Beverage": 70.0,
        "Home Goods": 65.0,
        "Outdoor": 60.0,
        "Apparel": 60.0,
        "Pet": 60.0,
        "Beauty": 55.0,
        "Personal Care": 55.0,
        "Childcare": 55.0,
        "Wellness": 50.0,
        "Consumer Tech": 45.0,
    }.get(category, 55.0)
    capital_intensity = _clamp(base_capital + (sku_proxy / 120) * 6 - engagement_quality * 8, 10, 95)

    # Heat and risk scores (0-100) aligned to PDF, but computed strictly from retrieved signals.
    growth_velocity = _clamp((instagram + tiktok) * 10 + momentum_hits * 3, 0, 100)
    sentiment_score = _clamp(55 + momentum_hits * 5 - risk_hits * 8, 0, 100)
    geographic_spread = _clamp(45 + blogs * 6 + reddit * 4, 0, 100)

    heat_score = _clamp(
        0.30 * growth_velocity
        + 0.20 * (engagement_quality * 100)
        + 0.15 * ugc_reposts
        + 0.15 * sentiment_score
        + 0.10 * influencer_overlap
        + 0.10 * geographic_spread,
        5,
        99.9,
    )
    risk_score = _clamp(18 + risk_hits * 18 + (1 - engagement_quality) * 38, 5, 98)
    asymmetry = _clamp(heat_score * 0.72 + (100 - risk_score) * 0.28 - capital_intensity * 0.10 + 8, 5, 98)

    capital_required = _clamp(2.0 + annual_rev_musd * (0.06 + capital_intensity / 800), 1.0, 120.0)

    return {
        "instagram_follower_velocity": float(_clamp(instagram * 10.0, 0.0, 100.0)),
        "tiktok_follower_velocity": float(_clamp(tiktok * 10.0, 0.0, 100.0)),
        "engagement_rate": float(engagement_rate),
        "comments_to_likes_ratio": float(comments_to_likes),
        "repeat_commenter_density": float(repeat_density),
        "influencer_tag_overlap": float(influencer_overlap),
        "ugc_repost_frequency": float(ugc_reposts),
        "engagement_quality": float(engagement_quality),
        "website_traffic_k": float(traffic_k),
        "sku_count": float(_clamp(sku_proxy, 1, 2000)),
        "sellout_velocity": float(sellout),
        "meta_ad_activity": float(meta_ads),
        "hiring_velocity": float(hiring),
        "stockist_expansion": float(stockists),
        "google_trends_velocity": float(google_trends),
        "reddit_mentions": float(reddit_mentions),
        "pinterest_saves_velocity": float(pinterest_saves),
        "blog_mentions": float(blog_mentions),
        "resale_activity": float(resale_activity),
        "heat_score": float(heat_score),
        "risk_score": float(risk_score),
        "asymmetry_index": float(asymmetry),
        "capital_intensity": float(capital_intensity),
        "revenue_p10": float(rev_p10),
        "revenue_p50": float(annual_rev_musd),
        "revenue_p90": float(rev_p90),
        "capital_required_musd": float(capital_required),
        "momentum_hits": float(momentum_hits),
        "risk_hits": float(risk_hits),
    }


def reset_all_data(db: Session) -> None:
    db.execute(delete(models.GeneratedReport))
    db.execute(delete(models.TimeSeriesPoint))
    db.execute(delete(models.EvidenceCitation))
    db.execute(delete(models.Scorecard))
    db.execute(delete(models.Brand))
    db.commit()


def _legacy_synthetic_present(db: Session) -> bool:
    """
    Detect legacy synthetic datasets from early PoC iterations.
    If present, we wipe the DB so the universe is rebuilt from real retrieval.
    """
    brand_total = int(db.query(func.count(models.Brand.id)).scalar() or 0)
    brand_ids = [row[0] for row in db.query(models.Brand.id).limit(5000).all()]
    for bid in brand_ids:
        # Legacy seed used "brand-001" style identifiers.
        if re.fullmatch(r"brand-\d{3}", bid or ""):
            return True

    bad_url_fragments = ("search.local", "registry.example", "news.example")
    evidence_urls = [row[0] for row in db.query(models.EvidenceCitation.url).limit(5000).all()]
    for url in evidence_urls:
        if url and any(fragment in url for fragment in bad_url_fragments):
            return True

    # Heuristic: synthetic datasets often have very low evidence coverage (or no brand-site corroboration).
    if brand_total >= 20:
        evidence_brand_count = int(db.query(func.count(func.distinct(models.EvidenceCitation.brand_id))).scalar() or 0)
        if evidence_brand_count < int(brand_total * 0.35):
            return True
    return False


def refresh_universe_snapshot(
    *,
    db: Session,
    router: SourceRouter,
    target_brands: int = 200,
    enrich_top_n: int = 30,
) -> dict[str, int | str]:
    """
    Build or refresh the current-week snapshot using only real web retrieval (SearXNG + site metadata).
    No synthetic seeding is performed.
    """
    snapshot_week = _monday_of_week()

    if _legacy_synthetic_present(db):
        reset_all_data(db)

    # Build universe if empty.
    existing = db.query(func.count(models.Brand.id)).scalar() or 0
    created = 0
    updated = 0

    if existing < 5:
        candidates = _collect_universe_candidates(router)
        ranked = _rank_candidates(candidates.values())[: max(25, target_brands)]
        metadata_fetch_limit = max(30, enrich_top_n)

        for idx, agg in enumerate(ranked):
            site_url = _canonical_site_url(agg.host)
            final_url = site_url
            title = ""
            desc = ""
            if idx < metadata_fetch_limit:
                final_url, title, desc = _fetch_site_metadata(site_url)
            final_host = _host(final_url) or agg.host
            seed_context = " ".join(
                f"{row.get('title', '')} {row.get('snippet', '')}" for row in agg.seed_evidence[:3] if isinstance(row, dict)
            )
            if _looks_like_publisher(title, desc or seed_context):
                continue

            name = _name_from_title_tag(title) or _fallback_brand_name(final_host)
            entity_key = entity_key_from_name(name) or _domain_label(final_host)
            brand_id_from_host = _stable_brand_id(final_host)
            description = desc
            if not description:
                for row in agg.seed_evidence:
                    snippet = (row.get("snippet") or "").strip()
                    if snippet:
                        description = snippet[:600]
                        break
            description = description or ""
            category = agg.primary_category
            region = "Global"

            brand = db.query(models.Brand).filter(models.Brand.id == brand_id_from_host).one_or_none()
            # Entity-resolution pass: if this host is a duplicate of an existing brand name, merge into that row.
            if not brand and entity_key:
                brand = db.query(models.Brand).filter(models.Brand.entity_key == entity_key).one_or_none()
            brand_id = brand.id if brand else brand_id_from_host
            if brand:
                # Name: prefer the longer / less-generic string.
                if len((name or "").strip()) >= len((brand.name or "").strip()):
                    brand.name = name
                brand.entity_key = entity_key
                # Website: avoid overwriting a canonical site with social/publisher hosts.
                existing_host = _host(brand.website or "")
                candidate_host = _host(final_url or "")
                if not brand.website:
                    brand.website = final_url
                elif existing_host == candidate_host:
                    brand.website = final_url
                elif (_is_excluded_host(existing_host) or _is_publisher_host(existing_host)) and not (
                    _is_excluded_host(candidate_host) or _is_publisher_host(candidate_host)
                ):
                    brand.website = final_url

                # Description: keep the richer text.
                if len((description or "").strip()) >= len((brand.description or "").strip()):
                    brand.description = description
                brand.category = category
                brand.region = region
                updated += 1
            else:
                db.add(
                    models.Brand(
                        id=brand_id,
                        name=name,
                        entity_key=entity_key,
                        category=category,
                        region=region,
                        website=final_url,
                        description=description,
                    )
                )
                created += 1

            # Seed minimal evidence from the universe lane results (real URLs).
            seed_seen = {
                row[0]
                for row in db.query(models.EvidenceCitation.url).filter(models.EvidenceCitation.brand_id == brand_id).all()
            }
            for row in agg.seed_evidence[:3]:
                if row["url"] in seed_seen:
                    continue
                seed_seen.add(row["url"])
                db.add(
                    models.EvidenceCitation(
                        brand_id=brand_id,
                        title=row["title"],
                        url=row["url"],
                        snippet=row["snippet"],
                        source=row["source"] or "searxng",
                        reliability=round(_source_reliability(row["source"]), 3),
                    )
                )

        db.commit()

    # Score snapshot for the current week.
    brands = db.query(models.Brand).all()
    if not brands:
        return {"status": "ok", "brands": 0, "created": created, "updated": updated, "snapshots": 0}

    # Backfill entity keys to improve dedupe across older rows.
    dirty = False
    for b in brands:
        if not (b.entity_key or "").strip():
            b.entity_key = entity_key_from_name(b.name) or _domain_label(_host(b.website))
            dirty = True
    if dirty:
        db.commit()

    # Pre-rank by current evidence lane appearance (cheap) to decide which brands get deeper enrichment.
    brand_ids = [b.id for b in brands]
    eligible = (
        db.query(models.EvidenceCitation.brand_id, func.count(models.EvidenceCitation.id))
        .filter(models.EvidenceCitation.brand_id.in_(brand_ids))
        .group_by(models.EvidenceCitation.brand_id)
        .order_by(func.count(models.EvidenceCitation.id).desc())
        .all()
    )
    enrich_set = {row[0] for row in eligible[:enrich_top_n]} if eligible else set(brand_ids[:enrich_top_n])

    snapshots_written = 0
    for brand in brands[:target_brands]:
        # Retrieval: brand context + site depth (both real web).
        provider, evidence = router.search(query=f"\"{brand.name}\" {brand.website}", limit=20)
        provider2, traffic = router.search(query=f"site:{_host(brand.website)}", limit=20)
        _ = (provider, provider2)

        extra_evidence_rows: list[dict[str, str]] = []
        if brand.id in enrich_set:
            # Pull in additional evidence specifically relevant to production/cost-down angles.
            _, prod = router.search(
                query=f"\"{brand.name}\" manufacturing sourcing supplier co-packer 3pl fulfillment packaging",
                limit=10,
            )
            _, site_prod = router.search(
                query=f"site:{_host(brand.website)} \"made in\" manufacturing sourcing packaging fulfillment",
                limit=10,
            )
            extra_evidence_rows = [
                {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source}
                for r in (list(prod) + list(site_prod))
                if r.url
            ]

        evidence_rows = [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source} for r in evidence if r.url
        ]
        traffic_rows = [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source} for r in traffic if r.url
        ]

        sku_count, median_price = _try_shopify_products(brand.website)
        metrics = _compute_snapshot_metrics(
            category=brand.category,
            evidence_results=evidence_rows,
            traffic_results=traffic_rows,
            brand_host=_host(brand.website),
            sku_count=sku_count,
            median_price_usd=median_price,
        )

        # Delta vs previous week.
        prev = (
            db.query(models.Scorecard)
            .filter(models.Scorecard.brand_id == brand.id, models.Scorecard.snapshot_week < snapshot_week)
            .order_by(models.Scorecard.snapshot_week.desc())
            .first()
        )
        delta_heat = float(metrics["heat_score"] - (prev.heat_score if prev else metrics["heat_score"]))

        # Confidence: count sources + whether we could observe products/pricing.
        unique_sources = {(_host(r["url"]) or r.get("source", "")).lower() for r in (evidence_rows + traffic_rows) if r.get("url")}
        evidence_count = len({r["url"] for r in evidence_rows})
        confidence = _clamp(
            0.38
            + min(0.22, evidence_count / 60)
            + min(0.18, len(unique_sources) / 40)
            + (0.14 if sku_count is not None else 0.0),
            0.25,
            0.93,
        )
        reasons = [
            "cross-source corroboration" if len(unique_sources) >= 6 else "limited cross-source corroboration",
            "commerce observability via product catalog" if sku_count is not None else "commerce observability limited",
            "momentum terms present" if metrics["momentum_hits"] >= 2 else "momentum terms sparse",
        ]

        # Deal structure (same rule-set as v1; inputs are now real-signal-derived).
        suggested = _deal_structure(
            metrics["heat_score"],
            metrics["risk_score"],
            metrics["asymmetry_index"],
            metrics["capital_required_musd"],
        )

        existing_score = (
            db.query(models.Scorecard)
            .filter(models.Scorecard.brand_id == brand.id, models.Scorecard.snapshot_week == snapshot_week)
            .one_or_none()
        )
        if existing_score:
            existing_score.heat_score = round(metrics["heat_score"], 3)
            existing_score.risk_score = round(metrics["risk_score"], 3)
            existing_score.asymmetry_index = round(metrics["asymmetry_index"], 3)
            existing_score.capital_intensity = round(metrics["capital_intensity"], 3)
            existing_score.revenue_p10 = round(metrics["revenue_p10"], 3)
            existing_score.revenue_p50 = round(metrics["revenue_p50"], 3)
            existing_score.revenue_p90 = round(metrics["revenue_p90"], 3)
            existing_score.delta_heat = round(delta_heat, 3)
            existing_score.confidence = round(confidence, 3)
            existing_score.confidence_reasons = reasons
            existing_score.suggested_deal_structure = suggested
            existing_score.capital_required_musd = round(metrics["capital_required_musd"], 3)
        else:
            db.add(
                models.Scorecard(
                    brand_id=brand.id,
                    snapshot_week=snapshot_week,
                    heat_score=round(metrics["heat_score"], 3),
                    risk_score=round(metrics["risk_score"], 3),
                    asymmetry_index=round(metrics["asymmetry_index"], 3),
                    capital_intensity=round(metrics["capital_intensity"], 3),
                    revenue_p10=round(metrics["revenue_p10"], 3),
                    revenue_p50=round(metrics["revenue_p50"], 3),
                    revenue_p90=round(metrics["revenue_p90"], 3),
                    delta_heat=round(delta_heat, 3),
                    confidence=round(confidence, 3),
                    confidence_reasons=reasons,
                    suggested_deal_structure=suggested,
                    capital_required_musd=round(metrics["capital_required_musd"], 3),
                )
            )

        # Time series points: store computed proxy metrics daily (so sparklines show motion within a week).
        # Upsert by (brand, metric, observed_at).
        observed = dt.date.today()
        for metric_name in [
            "heat",
            "instagram_follower_velocity",
            "tiktok_follower_velocity",
            "engagement_rate",
            "comments_to_likes_ratio",
            "repeat_commenter_density",
            "influencer_tag_overlap",
            "ugc_repost_frequency",
            "engagement_quality",
            "website_traffic_k",
            "sku_count",
            "sellout_velocity",
            "meta_ad_activity",
            "hiring_velocity",
            "stockist_expansion",
            "google_trends_velocity",
            "reddit_mentions",
            "pinterest_saves_velocity",
            "blog_mentions",
            "resale_activity",
        ]:
            value = float(metrics.get(metric_name) or 0.0)
            if metric_name == "heat":
                value = float(metrics["heat_score"])

            existing_point = (
                db.query(models.TimeSeriesPoint)
                .filter(
                    models.TimeSeriesPoint.brand_id == brand.id,
                    models.TimeSeriesPoint.metric == metric_name,
                    models.TimeSeriesPoint.observed_at == observed,
                )
                .one_or_none()
            )
            if existing_point:
                existing_point.value = round(value, 3)
                existing_point.source = "searxng"
                existing_point.reliability = round(0.55 + confidence * 0.4, 3)
            else:
                db.add(
                    models.TimeSeriesPoint(
                        brand_id=brand.id,
                        metric=metric_name,
                        observed_at=observed,
                        value=round(value, 3),
                        source="searxng",
                        reliability=round(0.55 + confidence * 0.4, 3),
                    )
                )

        # Evidence: keep it real and deduped. Store a small baseline for all brands, and deeper evidence for the top set.
        evidence_cap = 12 if brand.id in enrich_set else 4
        seen = {row[0] for row in db.query(models.EvidenceCitation.url).filter(models.EvidenceCitation.brand_id == brand.id).all()}
        store_candidates = (evidence_rows + extra_evidence_rows)[:evidence_cap]
        for r in store_candidates:
            if not r["url"] or r["url"] in seen:
                continue
            seen.add(r["url"])
            db.add(
                models.EvidenceCitation(
                    brand_id=brand.id,
                    title=_clean_text(r["title"])[:240] or brand.name,
                    url=_clean_text(r["url"])[:500],
                    snippet=_clean_text(r["snippet"])[:600],
                    source=_clean_text(r.get("source", "searxng"))[:120],
                    reliability=round(_source_reliability(r.get("source", "searxng")), 3),
                )
            )

        snapshots_written += 1

    db.commit()
    return {
        "status": "ok",
        "brands": int(db.query(func.count(models.Brand.id)).scalar() or 0),
        "created": int(created),
        "updated": int(updated),
        "snapshots": int(snapshots_written),
    }


def reseed_universe(
    *,
    db: Session,
    router: SourceRouter,
    target_brands: int = 200,
    enrich_top_n: int = 30,
) -> dict[str, int | str]:
    reset_all_data(db)
    return refresh_universe_snapshot(db=db, router=router, target_brands=target_brands, enrich_top_n=enrich_top_n)
