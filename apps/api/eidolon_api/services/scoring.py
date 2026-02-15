from __future__ import annotations

import datetime as dt
import re
from statistics import fmean

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from .production import (
    ProductionInputs,
    build_cost_reduction_opportunities,
    build_production_options,
    build_production_snapshot,
)

SORT_MAP = {
    "heat": desc(models.Scorecard.heat_score),
    "asymmetry": desc(models.Scorecard.asymmetry_index),
    "risk": desc(models.Scorecard.risk_score),
    "revenue": desc(models.Scorecard.revenue_p50),
    "capital_required": desc(models.Scorecard.capital_required_musd),
}

AOV_BY_CATEGORY = {
    "Beauty": 52.0,
    "Personal Care": 38.0,
    "Food & Beverage": 27.0,
    "Apparel": 84.0,
    "Home Goods": 96.0,
    "Consumer Tech": 168.0,
    "Pet": 44.0,
    "Outdoor": 122.0,
    "Childcare": 64.0,
    "Wellness": 58.0,
}

SOCIAL_SIGNAL_CONFIG: list[tuple[str, str, str]] = [
    ("instagram_follower_velocity", "Instagram follower velocity", "social_proxy"),
    ("tiktok_follower_velocity", "TikTok follower velocity", "social_proxy"),
    ("engagement_rate", "Engagement rate", "engagement_proxy"),
    ("comments_to_likes_ratio", "Comments-to-likes ratio", "engagement_proxy"),
    ("repeat_commenter_density", "Repeat commenter density", "engagement_proxy"),
    ("influencer_tag_overlap", "Influencer tag overlap", "network_proxy"),
    ("ugc_repost_frequency", "UGC repost frequency", "ugc_proxy"),
]

COMMERCE_SIGNAL_CONFIG: list[tuple[str, str, str]] = [
    ("website_traffic_k", "Website traffic estimate (k/mo)", "commerce_proxy"),
    ("sku_count", "SKU count", "commerce_proxy"),
    ("sellout_velocity", "Sellout velocity", "commerce_proxy"),
    ("meta_ad_activity", "Meta Ad Library activity", "ad_proxy"),
    ("hiring_velocity", "Hiring velocity", "hiring_proxy"),
    ("stockist_expansion", "Retail stockist expansion", "retail_proxy"),
]

SEARCH_CULTURAL_SIGNAL_CONFIG: list[tuple[str, str, str]] = [
    ("google_trends_velocity", "Google Trends velocity", "search_proxy"),
    ("reddit_mentions", "Reddit mention frequency", "reddit"),
    ("pinterest_saves_velocity", "Pinterest saves velocity", "search_proxy"),
    ("blog_mentions", "Substack/blog mentions", "news"),
    ("resale_activity", "Resale platform activity", "market_proxy"),
]

TRAILING_VERSION_RE = re.compile(r"\s+\d+$")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _canonical_company_name(name: str) -> str:
    normalized = " ".join(name.split()).strip()
    canonical = TRAILING_VERSION_RE.sub("", normalized)
    return canonical or normalized


def _avg_metric(points: list[models.TimeSeriesPoint], metric: str, default: float) -> float:
    values = [p.value for p in points if p.metric == metric]
    if not values:
        return default
    return float(fmean(values))


def _metric_current_and_delta(points: list[models.TimeSeriesPoint], metric: str, default: float) -> tuple[float, float]:
    metric_points = [p for p in points if p.metric == metric]
    if not metric_points:
        return default, 0.0

    ordered = sorted(metric_points, key=lambda p: p.observed_at)
    first = ordered[0].value
    last = ordered[-1].value
    return float(last), float(last - first)


def _risk_bucket(value: float) -> str:
    if value < 36:
        return "low"
    if value < 68:
        return "medium"
    return "high"


def _ownership_target_for_structure(structure: str) -> str:
    mapping = {
        "Minority growth investment": "15%-30%",
        "Control acquisition": "51%-70%",
        "IP partnership": "20%-35%",
        "Licensing structure": "5%-15% royalty + call option",
        "Debt plus earnout": "20%-40% equity equivalent",
    }
    return mapping.get(structure, "20%-35%")


def _deeper_analysis_required(heat_score: float) -> bool:
    return heat_score >= 75.0


def _build_engagement_breakdown(
    score: models.Scorecard,
    points: list[models.TimeSeriesPoint],
) -> schemas.EngagementBreakdown:
    avg_engagement_quality = _avg_metric(points, metric="engagement_quality", default=0.86)

    comments_to_likes = _clamp(0.03 + avg_engagement_quality * 0.1, 0.03, 0.35)
    repeat_commenter_density = _clamp(0.18 + score.heat_score / 160 + score.confidence * 0.2, 0.15, 0.92)
    ugc_depth_score = _clamp(score.heat_score * 0.72 + score.delta_heat * 1.8, 5.0, 99.0)
    sentiment_score = _clamp(58 + score.heat_score * 0.28 - score.risk_score * 0.32, 5.0, 99.0)
    influencer_overlap_score = _clamp(35 + score.heat_score * 0.35 + score.asymmetry_index * 0.25, 5.0, 99.0)
    geographic_spread_score = _clamp(24 + score.heat_score * 0.42 - score.risk_score * 0.12, 5.0, 99.0)

    return schemas.EngagementBreakdown(
        comments_to_likes_ratio=round(comments_to_likes, 3),
        repeat_commenter_density=round(repeat_commenter_density, 3),
        ugc_depth_score=round(ugc_depth_score, 2),
        sentiment_score=round(sentiment_score, 2),
        influencer_overlap_score=round(influencer_overlap_score, 2),
        geographic_spread_score=round(geographic_spread_score, 2),
    )


def _build_signal_snapshot(points: list[models.TimeSeriesPoint]) -> schemas.DataCollectionLayerSnapshot:
    social = [
        schemas.SignalPoint(
            metric=label,
            current=round(_metric_current_and_delta(points, metric=metric, default=0.0)[0], 3),
            delta_12w=round(_metric_current_and_delta(points, metric=metric, default=0.0)[1], 3),
            source=source,
        )
        for metric, label, source in SOCIAL_SIGNAL_CONFIG
    ]
    commerce = [
        schemas.SignalPoint(
            metric=label,
            current=round(_metric_current_and_delta(points, metric=metric, default=0.0)[0], 3),
            delta_12w=round(_metric_current_and_delta(points, metric=metric, default=0.0)[1], 3),
            source=source,
        )
        for metric, label, source in COMMERCE_SIGNAL_CONFIG
    ]
    search_cultural = [
        schemas.SignalPoint(
            metric=label,
            current=round(_metric_current_and_delta(points, metric=metric, default=0.0)[0], 3),
            delta_12w=round(_metric_current_and_delta(points, metric=metric, default=0.0)[1], 3),
            source=source,
        )
        for metric, label, source in SEARCH_CULTURAL_SIGNAL_CONFIG
    ]
    return schemas.DataCollectionLayerSnapshot(
        social_signals=social,
        commerce_signals=commerce,
        search_cultural_signals=search_cultural,
        acceleration_priority_note=(
            "Signals prioritize velocity and acceleration over absolute scale."
        ),
    )


def _build_financial_inference(score: models.Scorecard, category: str) -> schemas.FinancialInferenceModel:
    aov = AOV_BY_CATEGORY.get(category, 60.0)
    conversion_pct = _clamp(1.1 + score.heat_score / 58 - score.risk_score / 160, 0.7, 5.5)
    traffic_estimate_kmo = score.revenue_p50 * 1_000_000 / max(1.0, aov * (conversion_pct / 100)) / 1000
    sku_count_estimate = int(_clamp(round(score.revenue_p50 * 1.7 + score.capital_intensity * 0.55), 10, 600))
    sell_through_pct = _clamp(52 + score.heat_score * 0.3 - score.risk_score * 0.16, 30, 97)
    gross_margin_pct = _clamp(28 + score.asymmetry_index * 0.31 - score.capital_intensity * 0.11, 15, 87)
    cac_proxy_usd = _clamp(aov * (0.34 + score.risk_score / 240 + score.capital_intensity / 300), 7, 350)
    ltv_proxy_usd = _clamp(aov * (1.6 + score.heat_score / 70 + score.asymmetry_index / 130), 35, 1800)

    flags: list[str] = []
    if score.heat_score >= 75 and score.revenue_p50 < 25:
        flags.append("High Heat with Low Revenue")
    if score.revenue_p50 >= 80 and score.capital_intensity >= 55:
        flags.append("High Revenue with Operational Inefficiency")
    if score.revenue_p50 >= 70 and score.asymmetry_index >= 65:
        flags.append("High Revenue with Underleveraged IP")
    if not flags:
        flags.append("No critical financial asymmetry flags triggered.")

    notes = [
        "Revenue proxy uses traffic x conversion x average order value baseline.",
        "Cross-check includes SKU x price x estimated sell-through.",
        "Hiring/ad-activity momentum is treated as directional, not definitive.",
    ]

    return schemas.FinancialInferenceModel(
        traffic_estimate_kmo=round(traffic_estimate_kmo, 2),
        conversion_assumption_pct=round(conversion_pct, 2),
        average_order_value_usd=round(aov, 2),
        sku_count_estimate=sku_count_estimate,
        sell_through_assumption_pct=round(sell_through_pct, 2),
        gross_margin_estimate_pct=round(gross_margin_pct, 2),
        cac_proxy_usd=round(cac_proxy_usd, 2),
        ltv_proxy_usd=round(ltv_proxy_usd, 2),
        scenario_flags=flags,
        inference_notes=notes,
    )


def _build_risk_scan(
    score: models.Scorecard,
    evidence: list[models.EvidenceCitation],
    production_snapshot: schemas.ProductionSnapshot,
) -> schemas.RiskScanSummary:
    registry_verified = any(item.source == "public_registry" for item in evidence)

    if registry_verified and score.risk_score < 45:
        trademark_strength = "strong"
    elif score.risk_score < 70:
        trademark_strength = "moderate"
    else:
        trademark_strength = "weak"

    litigation_flags: list[str]
    if score.risk_score > 78:
        litigation_flags = [
            "Potential litigation sensitivity detected in claims, labeling, or IP perimeter.",
            "Manual legal counsel review recommended before outreach escalation.",
        ]
    elif score.risk_score > 62:
        litigation_flags = ["Moderate legal sensitivity; verify trademark classes and open disputes."]
    else:
        litigation_flags = ["No active litigation flags detected in available public signals."]

    platform_dependency_raw = score.risk_score * 0.55 + (100 - score.asymmetry_index) * 0.45
    algorithm_exposure_raw = score.heat_score * 0.62 + abs(score.delta_heat) * 6.0
    supplier_concentration_raw = score.capital_intensity * 0.7 + score.risk_score * 0.3

    founder_dependency_score = _clamp(
        28 + score.asymmetry_index * 0.38 + max(0.0, 80 - score.revenue_p50) * 0.18,
        8.0,
        98.0,
    )

    key_risks = [
        f"Platform dependency risk is {_risk_bucket(platform_dependency_raw)}.",
        f"Algorithm exposure risk is {_risk_bucket(algorithm_exposure_raw)}.",
        f"Supplier concentration risk is {_risk_bucket(supplier_concentration_raw)}.",
        f"Primary operational bottleneck: {production_snapshot.bottlenecks[0]}",
    ]

    return schemas.RiskScanSummary(
        trademark_strength=trademark_strength,  # type: ignore[arg-type]
        corporate_registry_verified=registry_verified,
        litigation_flags=litigation_flags,
        platform_dependency_risk=_risk_bucket(platform_dependency_raw),  # type: ignore[arg-type]
        algorithm_exposure_risk=_risk_bucket(algorithm_exposure_raw),  # type: ignore[arg-type]
        supplier_concentration_risk=_risk_bucket(supplier_concentration_raw),  # type: ignore[arg-type]
        founder_dependency_score=round(founder_dependency_score, 2),
        key_risks=key_risks,
    )


def _build_founder_alignment_thesis(
    brand_name: str,
    score: models.Scorecard,
    deeper_analysis_required: bool,
) -> str:
    tone = "high-urgency" if deeper_analysis_required else "measured"
    return (
        f"{brand_name} appears founder-led with a {tone} opportunity to align on growth while preserving brand voice. "
        f"Anchor around safeguarding creative control, improving operating cadence, and using capital against "
        f"the highest-friction constraint (risk={score.risk_score:.1f}, asymmetry={score.asymmetry_index:.1f})."
    )


def _build_outreach_email(
    brand_name: str,
    suggested_deal_structure: str,
    ownership_target: str,
    capital_required_musd: float,
) -> str:
    return (
        f"Subject: {brand_name} growth partnership discussion\\n\\n"
        "Hi [Founder Name],\\n\\n"
        f"We've been tracking {brand_name}'s acceleration and see strong potential to support the next phase of growth. "
        f"Our initial view is a {suggested_deal_structure.lower()} with a target stake of {ownership_target} and "
        f"about ${capital_required_musd:.1f}M of growth capital.\\n\\n"
        "If helpful, we can share a concise operating blueprint covering supply-chain resilience, "
        "COGS reduction levers, and scenario-tested downside protections.\\n\\n"
        "Would you be open to a short intro call next week?\\n\\n"
        "Best,\\nBURCH-EIDOLON"
    )


def get_latest_snapshot_week(db: Session) -> dt.date:
    latest = db.query(func.max(models.Scorecard.snapshot_week)).scalar()
    return latest


def build_feed(
    db: Session,
    sort: schemas.SortMode = "heat",
    limit: int = 200,
    search: str | None = None,
    time_window: str = "12w",
) -> schemas.FeedResponse:
    _ = time_window
    latest_week = get_latest_snapshot_week(db)
    if latest_week is None:
        return schemas.FeedResponse(generated_at=dt.datetime.now(dt.UTC), sort=sort, items=[])

    query = (
        db.query(models.Brand, models.Scorecard)
        .join(models.Scorecard, models.Brand.id == models.Scorecard.brand_id)
        .filter(models.Scorecard.snapshot_week == latest_week)
    )

    if search:
        tokens = [tok for tok in re.split(r"\s+", search.strip()) if tok]
        if tokens:
            clauses = []
            for tok in tokens:
                term = f"%{tok}%"
                clauses.append(
                    models.Brand.name.ilike(term)
                    | models.Brand.category.ilike(term)
                    | models.Brand.region.ilike(term)
                    | models.Brand.website.ilike(term)
                )
            query = query.filter(or_(*clauses))

    order_by = SORT_MAP.get(sort, SORT_MAP["heat"])
    rows = query.order_by(order_by, desc(models.Scorecard.confidence)).all()

    items: list[schemas.BrandSummary] = []
    seen_entities: set[str] = set()
    for brand, score in rows:
        display_name = _canonical_company_name(brand.name)
        entity_key = display_name.lower()
        if entity_key in seen_entities:
            continue
        seen_entities.add(entity_key)

        rank = len(items) + 1
        items.append(
            schemas.BrandSummary(
                rank=rank,
                brand_id=brand.id,
                name=display_name,
                category=brand.category,
                region=brand.region,
                heat_score=round(score.heat_score, 2),
                risk_score=round(score.risk_score, 2),
                asymmetry_index=round(score.asymmetry_index, 2),
                capital_intensity=round(score.capital_intensity, 2),
                revenue_p50=round(score.revenue_p50, 2),
                capital_required_musd=round(score.capital_required_musd, 2),
                delta_heat=round(score.delta_heat, 2),
                confidence=round(score.confidence, 3),
                deeper_analysis_required=_deeper_analysis_required(score.heat_score),
            )
        )
        if len(items) >= limit:
            break

    return schemas.FeedResponse(generated_at=dt.datetime.now(dt.UTC), sort=sort, items=items)


def build_brand_profile(db: Session, brand_id: str) -> schemas.BrandProfile:
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).one_or_none()
    if not brand:
        raise ValueError(f"Unknown brand_id={brand_id}")

    score = (
        db.query(models.Scorecard)
        .filter(models.Scorecard.brand_id == brand_id)
        .order_by(desc(models.Scorecard.snapshot_week))
        .first()
    )
    if not score:
        raise ValueError(f"No scorecard for brand_id={brand_id}")

    evidence = (
        db.query(models.EvidenceCitation)
        .filter(models.EvidenceCitation.brand_id == brand_id)
        .order_by(desc(models.EvidenceCitation.reliability))
        .limit(8)
        .all()
    )
    points = (
        db.query(models.TimeSeriesPoint)
        .filter(models.TimeSeriesPoint.brand_id == brand_id)
        .order_by(models.TimeSeriesPoint.observed_at.asc())
        .all()
    )

    display_name = _canonical_company_name(brand.name)

    confidence = schemas.ConfidenceEnvelope(
        overall=round(score.confidence, 3),
        reasons=list(score.confidence_reasons or []),
    )
    deeper_analysis_required = _deeper_analysis_required(score.heat_score)

    production_inputs = ProductionInputs(
        category=brand.category,
        heat_score=score.heat_score,
        risk_score=score.risk_score,
        asymmetry_index=score.asymmetry_index,
        capital_intensity=score.capital_intensity,
        revenue_p50=score.revenue_p50,
        confidence=score.confidence,
    )
    production_snapshot = build_production_snapshot(production_inputs)
    production_options = build_production_options(production_inputs)
    cost_reduction = build_cost_reduction_opportunities(production_inputs)
    signal_snapshot = _build_signal_snapshot(points=points)
    engagement_breakdown = _build_engagement_breakdown(score=score, points=points)
    financial_inference = _build_financial_inference(score=score, category=brand.category)
    risk_scan = _build_risk_scan(score=score, evidence=evidence, production_snapshot=production_snapshot)
    ownership_target = _ownership_target_for_structure(score.suggested_deal_structure)
    founder_alignment = _build_founder_alignment_thesis(
        brand_name=display_name,
        score=score,
        deeper_analysis_required=deeper_analysis_required,
    )
    outreach_email = _build_outreach_email(
        brand_name=display_name,
        suggested_deal_structure=score.suggested_deal_structure,
        ownership_target=ownership_target,
        capital_required_musd=score.capital_required_musd,
    )
    deal_structuring = schemas.DealStructuringPlan(
        suggested_entry_strategy=score.suggested_deal_structure,
        suggested_ownership_target_pct=ownership_target,
        estimated_capital_required_musd=round(score.capital_required_musd, 2),
        founder_alignment_thesis=founder_alignment,
        draft_outreach_email=outreach_email,
        deeper_analysis_required=deeper_analysis_required,
    )

    memo_preview = (
        f"{display_name} shows heat {score.heat_score:.1f}, asymmetry {score.asymmetry_index:.1f}, and "
        f"risk {score.risk_score:.1f}. Revenue midpoint is ${score.revenue_p50:.1f}M with "
        f"capital requirement around ${score.capital_required_musd:.1f}M. "
        f"Suggested structure: {score.suggested_deal_structure} targeting {ownership_target}. "
        f"Current production model is {production_snapshot.current_model.lower()} with "
        f"{cost_reduction[0].estimated_savings_pct_low:.1f}% to {cost_reduction[0].estimated_savings_pct_high:.1f}% "
        "cost-down potential from the lead procurement lever."
    )

    return schemas.BrandProfile(
        brand=schemas.BrandData(
            id=brand.id,
            name=display_name,
            category=brand.category,
            region=brand.region,
            website=brand.website,
            description=brand.description,
        ),
        scorecard=schemas.ScoreCard(
            snapshot_week=score.snapshot_week,
            heat_score=round(score.heat_score, 2),
            risk_score=round(score.risk_score, 2),
            asymmetry_index=round(score.asymmetry_index, 2),
            capital_intensity=round(score.capital_intensity, 2),
            revenue_p10=round(score.revenue_p10, 2),
            revenue_p50=round(score.revenue_p50, 2),
            revenue_p90=round(score.revenue_p90, 2),
            delta_heat=round(score.delta_heat, 2),
            capital_required_musd=round(score.capital_required_musd, 2),
            suggested_deal_structure=score.suggested_deal_structure,
            deeper_analysis_required=deeper_analysis_required,
        ),
        confidence=confidence,
        evidence=[
            schemas.EvidenceCitation(
                title=e.title,
                url=e.url,
                source=e.source,
                snippet=e.snippet,
                reliability=round(e.reliability, 3),
            )
            for e in evidence
        ],
        production_snapshot=production_snapshot,
        production_options=production_options,
        cost_reduction_opportunities=cost_reduction,
        data_collection_snapshot=signal_snapshot,
        engagement_breakdown=engagement_breakdown,
        financial_inference=financial_inference,
        risk_scan=risk_scan,
        deal_structuring=deal_structuring,
        memo_preview=memo_preview,
    )


def get_timeseries(db: Session, brand_id: str) -> schemas.TimeSeriesResponse:
    points = (
        db.query(models.TimeSeriesPoint)
        .filter(models.TimeSeriesPoint.brand_id == brand_id)
        .order_by(models.TimeSeriesPoint.observed_at.asc())
        .all()
    )
    return schemas.TimeSeriesResponse(
        brand_id=brand_id,
        points=[
            schemas.TimeSeriesPoint(
                metric=p.metric,
                observed_at=p.observed_at,
                value=round(p.value, 3),
                source=p.source,
            )
            for p in points
        ],
    )
