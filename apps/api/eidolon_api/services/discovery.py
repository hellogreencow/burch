from __future__ import annotations

import datetime as dt
import re
from statistics import median
from urllib.parse import urlparse

from .. import schemas
from .providers.router import SourceRouter

TITLE_SPLIT_RE = re.compile(r"\s[-|:]\s")
WORD_RE = re.compile(r"[a-z0-9]+")

SOURCE_RELIABILITY = {
    "reddit": 0.72,
    "news": 0.78,
    "public_registry": 0.84,
    "searxng": 0.62,
    "google": 0.68,
    "bing": 0.66,
    "duckduckgo": 0.64,
}

MOMENTUM_TERMS = {
    "growth",
    "surge",
    "expansion",
    "viral",
    "record",
    "raised",
    "launch",
    "partnership",
    "opening",
    "scale",
    "scaled",
    "momentum",
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
    "default",
    "warning",
}

GENERIC_NAME_TERMS = {
    "best",
    "top",
    "guide",
    "list",
    "trend",
    "trends",
    "market",
    "markets",
    "industry",
    "insights",
    "news",
    "review",
    "reviews",
    "analysis",
    "report",
    "reports",
    "companies",
    "brands",
    "consumer",
    "startup",
    "startups",
}

LEGAL_SUFFIXES = {
    "inc",
    "llc",
    "ltd",
    "co",
    "company",
    "corp",
    "corporation",
    "plc",
    "gmbh",
    "srl",
}

PUBLISHER_HOST_HINTS = {
    "forbes",
    "techcrunch",
    "wikipedia",
    "reddit",
    "youtube",
    "linkedin",
    "substack",
    "bloomberg",
    "fortune",
    "medium",
    "nytimes",
    "wsj",
    "businessinsider",
    "theverge",
    "axios",
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _tokenize(value: str) -> set[str]:
    return {tok for tok in WORD_RE.findall(value.lower()) if len(tok) >= 3}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _source_weight(source: str) -> float:
    lowered = source.lower()
    for key, value in SOURCE_RELIABILITY.items():
        if key in lowered:
            return value
    return 0.58


def _domain_label(url: str) -> str:
    host = (urlparse(url).netloc or "").lower().split(":", 1)[0]
    if not host:
        return ""
    parts = [p for p in host.split(".") if p and p != "www"]
    if not parts:
        return ""
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net"}:
        core = parts[-3]
    elif len(parts) >= 2:
        core = parts[-2]
    else:
        core = parts[0]
    return re.sub(r"[^a-z0-9]+", " ", core).strip()


def _title_case_words(value: str) -> str:
    words = [w for w in value.split() if w]
    return " ".join(w.capitalize() for w in words)


def _normalize_company_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    tokens = [tok for tok in cleaned.split() if tok and tok not in LEGAL_SUFFIXES]
    if len(tokens) > 6:
        tokens = tokens[:6]
    return " ".join(tokens)


def _is_generic_name(norm_name: str) -> bool:
    if not norm_name:
        return True
    tokens = norm_name.split()
    if len(tokens) <= 1:
        return True
    generic_hits = sum(1 for tok in tokens if tok in GENERIC_NAME_TERMS)
    return generic_hits >= max(1, len(tokens) // 2)


def _is_publisher_host(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(hint in host for hint in PUBLISHER_HOST_HINTS)


def _name_guess_from_title(title: str) -> str:
    cleaned = _clean_text(title)
    if not cleaned:
        return "Unknown"
    parts = TITLE_SPLIT_RE.split(cleaned)
    guess = parts[0] if parts else cleaned
    words = guess.split()
    if len(words) > 7:
        guess = " ".join(words[:7])
    return guess


def _derive_company_name(title: str, url: str) -> str:
    guess = _name_guess_from_title(title)
    norm_guess = _normalize_company_name(guess)
    domain_name = _title_case_words(_domain_label(url))

    if _is_generic_name(norm_guess):
        if domain_name and not _is_publisher_host(url):
            return domain_name
        return guess
    return guess


def _entity_key(company_name: str, url: str) -> str:
    norm_name = _normalize_company_name(company_name)
    domain = _normalize_company_name(_domain_label(url))
    if not norm_name or _is_generic_name(norm_name):
        return f"domain:{domain or 'unknown'}"
    short = " ".join(norm_name.split()[:3])
    return f"name:{short}"


def _query_plan(industry: str, region: str | None) -> list[str]:
    geo = f" {region}" if region else ""
    industry_clean = _clean_text(industry)
    return [
        f"emerging {industry_clean} consumer brand{geo}",
        f"{industry_clean} d2c brand growth{geo}",
        f"{industry_clean} startup retail expansion{geo}",
        f"{industry_clean} founder-led company momentum{geo}",
    ]


def _estimated_revenue_band(fit: float, momentum: float) -> str:
    composite = fit * 0.55 + momentum * 0.45
    if composite < 45:
        return "$5M-$20M"
    if composite < 60:
        return "$20M-$60M"
    if composite < 75:
        return "$60M-$150M"
    return "$150M-$350M"


def _deal_structure(fit: float, momentum: float, risk: float, asymmetry: float) -> str:
    if asymmetry >= 72 and risk <= 45:
        return "Minority growth investment"
    if risk >= 68:
        return "Licensing structure"
    if fit >= 70 and momentum >= 65:
        return "IP partnership"
    if asymmetry >= 66 and risk < 60:
        return "Debt plus earnout"
    return "Control acquisition"


def _production_cost_down_angle(industry: str) -> str:
    i = industry.lower()
    if "beauty" in i or "skin" in i or "cosmetic" in i or "personal care" in i:
        return "Contract fill-finish rebid plus packaging simplification to compress COGS."
    if "food" in i or "beverage" in i or "snack" in i:
        return "Co-packer lane optimization and ingredient contract rebid for procurement savings."
    if "apparel" in i or "fashion" in i or "outdoor" in i:
        return "Supplier portfolio rebalance with regionalized finishing to reduce material and freight pressure."
    if "home" in i or "furniture" in i:
        return "SKU architecture cleanup and 3PL lane optimization to lower landed cost volatility."
    if "tech" in i or "electronics" in i:
        return "OEM repricing and component dual-sourcing to lower unit cost risk."
    return "Strategic contract rebid and regional fulfillment optimization as primary cost-down lever."


def _score_company(
    candidate: schemas.DiscoveryCandidate,
    company_name: str,
    industry: str,
    region: str | None,
) -> schemas.DiscoveryCompanyReport:
    text = _clean_text(f"{company_name} {candidate.title} {candidate.snippet} {candidate.query}").lower()
    text_tokens = _tokenize(text)
    industry_tokens = _tokenize(industry)
    region_tokens = _tokenize(region or "")

    industry_overlap = len(text_tokens & industry_tokens) / max(1, len(industry_tokens))
    region_overlap = len(text_tokens & region_tokens) / max(1, len(region_tokens)) if region_tokens else 0.0

    source_weight = _source_weight(candidate.source)

    momentum_hits = sum(1 for t in MOMENTUM_TERMS if t in text_tokens)
    risk_hits = sum(1 for t in RISK_TERMS if t in text_tokens)

    fit_score = _clamp(42 + industry_overlap * 42 + region_overlap * 10 + source_weight * 10, 5, 99)
    momentum_score = _clamp(34 + momentum_hits * 8 + source_weight * 22, 5, 99)
    risk_score = _clamp(20 + risk_hits * 15 + (1 - source_weight) * 18, 5, 98)
    asymmetry_score = _clamp(fit_score * 0.5 + momentum_score * 0.35 - risk_score * 0.23 + 19, 5, 98)

    confidence = _clamp(0.42 + source_weight * 0.35 + fit_score / 260 + momentum_score / 320 - risk_score / 700, 0.3, 0.94)

    revenue_band = _estimated_revenue_band(fit_score, momentum_score)
    structure = _deal_structure(fit_score, momentum_score, risk_score, asymmetry_score)
    cost_down = _production_cost_down_angle(industry)

    opportunity = (
        f"{company_name} shows fit {fit_score:.1f} and momentum {momentum_score:.1f} in {industry.lower()} signals. "
        f"Asymmetry is estimated at {asymmetry_score:.1f} with risk {risk_score:.1f}; "
        f"best initial structure is {structure.lower()}."
    )
    next_step = (
        "Run full dossier pull: engagement breakdown, financial inference, risk scan, and founder outreach draft before outreach."
    )
    key_risks = [
        f"Signal-derived risk score sits at {risk_score:.1f}; validate legal/IP perimeter before term-sheet motion.",
        "Platform/channel concentration may amplify volatility; map channel mix and dependency caps.",
        "Supplier concentration and lead-time risk should be stress-tested under demand acceleration.",
    ]
    diligence_questions = [
        "What is the verified 12-month net revenue and gross margin trend by channel?",
        "Which suppliers represent >20% of COGS and what alternate capacity exists?",
        "What founder priorities are non-negotiable in ownership and governance design?",
    ]
    operational_cost_down_actions = [
        "Run strategic contract rebid across top spend categories and key manufacturing nodes.",
        "Regionalize fulfillment lanes to reduce freight volatility and shorten lead times.",
        "Simplify SKU and packaging architecture to reduce MOQ drag and conversion complexity.",
    ]
    execution_plan_30_60_90 = [
        "30d: build COGS baseline, supplier map, and channel economics view.",
        "60d: launch targeted RFPs, pilot dual-source options, and validate savings assumptions.",
        "90d: lock negotiated terms, rollout winning lanes, and track realized savings versus plan.",
    ]

    return schemas.DiscoveryCompanyReport(
        name=company_name,
        source_url=candidate.url,
        source=candidate.source,
        fit_score=round(fit_score, 2),
        momentum_score=round(momentum_score, 2),
        risk_score=round(risk_score, 2),
        asymmetry_score=round(asymmetry_score, 2),
        estimated_revenue_band=revenue_band,
        suggested_deal_structure=structure,
        production_cost_down_angle=cost_down,
        opportunity_thesis=opportunity,
        next_step=next_step,
        key_risks=key_risks,
        diligence_questions=diligence_questions,
        operational_cost_down_actions=operational_cost_down_actions,
        execution_plan_30_60_90=execution_plan_30_60_90,
        confidence=round(confidence, 3),
    )


def _report_rank(report: schemas.DiscoveryCompanyReport) -> float:
    return report.fit_score * 0.45 + report.asymmetry_score * 0.35 + report.confidence * 20 - report.risk_score * 0.2


def _build_top_signals(
    reports: list[schemas.DiscoveryCompanyReport],
    provider_attempts: list[str],
) -> list[str]:
    successful_attempts = [row for row in provider_attempts if not row.endswith("=> none")]
    if not reports:
        return ["No strong candidate signals yet."]

    median_fit = median([r.fit_score for r in reports])
    median_risk = median([r.risk_score for r in reports])
    median_asym = median([r.asymmetry_score for r in reports])
    top = reports[0]

    return [
        f"Successful query lanes: {len(successful_attempts)}/{len(provider_attempts)}.",
        f"Top candidate: {top.name} (fit {top.fit_score:.1f}, asymmetry {top.asymmetry_score:.1f}).",
        f"Median fit {median_fit:.1f}, median risk {median_risk:.1f}, median asymmetry {median_asym:.1f}.",
    ]


def _build_narrative(
    industry: str,
    region: str | None,
    reports: list[schemas.DiscoveryCompanyReport],
) -> str:
    if not reports:
        geo = f" in {region}" if region else ""
        return f"No high-confidence companies found for {industry}{geo}. Try broader terms or remove region filter."

    top = reports[:3]
    names = ", ".join(r.name for r in top)
    geo = f" in {region}" if region else ""
    return (
        f"Discovery pass for {industry}{geo} surfaced {len(reports)} unique candidate companies. "
        f"Highest-priority names are {names}. Focus first diligence on production cost-down leverage and ownership-fit alignment."
    )


def discover_companies(
    router: SourceRouter,
    industry: str,
    region: str | None = None,
    limit: int = 12,
) -> schemas.DiscoverResponse:
    industry_clean = _clean_text(industry)
    if not industry_clean:
        raise ValueError("industry must not be empty")

    region_clean = _clean_text(region) if region else None
    queries = _query_plan(industry=industry_clean, region=region_clean)
    per_query = max(3, min(10, (limit + len(queries) - 1) // len(queries)))

    provider_attempts: list[str] = []
    raw_rows: list[schemas.DiscoveryCandidate] = []
    seen_keys: set[str] = set()

    for query in queries:
        provider, results = router.search(query=query, limit=per_query)
        provider_attempts.append(f"{query} => {provider}")

        for result in results:
            url = _clean_text(result.url)
            title = _clean_text(result.title)
            snippet = _clean_text(result.snippet)
            if not url or not title:
                continue

            parsed = urlparse(url)
            dedupe_key = f"{parsed.netloc.lower()}|{title.lower()}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            company_name = _derive_company_name(title, url)

            raw_rows.append(
                schemas.DiscoveryCandidate(
                    name_guess=company_name,
                    title=title,
                    url=url,
                    snippet=snippet,
                    source=result.source,
                    query=query,
                )
            )

            if len(raw_rows) >= limit:
                break
        if len(raw_rows) >= limit:
            break

    raw_unique_rows: list[schemas.DiscoveryCandidate] = []
    seen_entity_rows: set[str] = set()
    for row in raw_rows:
        entity_key = _entity_key(row.name_guess, row.url)
        if entity_key in seen_entity_rows:
            continue
        seen_entity_rows.add(entity_key)
        raw_unique_rows.append(row)

    deduped_reports: dict[str, schemas.DiscoveryCompanyReport] = {}
    for row in raw_unique_rows:
        key = _entity_key(row.name_guess, row.url)
        report = _score_company(row, company_name=row.name_guess, industry=industry_clean, region=region_clean)

        if key not in deduped_reports:
            deduped_reports[key] = report
            continue

        if _report_rank(report) > _report_rank(deduped_reports[key]):
            deduped_reports[key] = report

    company_reports = list(deduped_reports.values())
    company_reports.sort(key=lambda r: (r.fit_score, r.asymmetry_score, -r.risk_score), reverse=True)

    top_signals = _build_top_signals(company_reports, provider_attempts)
    narrative = _build_narrative(industry_clean, region_clean, company_reports)

    return schemas.DiscoverResponse(
        generated_at=dt.datetime.now(dt.UTC),
        industry=industry_clean,
        region=region_clean,
        provider_attempts=provider_attempts,
        items=raw_unique_rows[:limit],
        report=schemas.IndustryReport(
            industry=industry_clean,
            region=region_clean,
            narrative=narrative,
            top_signals=top_signals,
            company_reports=company_reports[: max(1, min(10, limit))],
        ),
    )
