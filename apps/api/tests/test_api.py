import re

import pytest
from fastapi.testclient import TestClient

import datetime as dt

from eidolon_api import models
from eidolon_api.config import Settings
from eidolon_api.database import SessionLocal
from eidolon_api.main import app
from eidolon_api.services.chat import ChatService
from eidolon_api.services.ingestion import reset_all_data


@pytest.fixture()
def client() -> TestClient:
    # Ensure tests do not rely on persisted local state.
    db = SessionLocal()
    try:
        reset_all_data(db)

        snapshot_week = dt.date.today()
        snapshot_week = snapshot_week - dt.timedelta(days=snapshot_week.weekday())

        # Deterministic, synthetic-for-tests-only dataset.
        categories = ["Outdoor", "Beauty", "Food & Beverage", "Apparel", "Home Goods"]
        for i in range(40):
            brand_id = f"brand-test-{i + 1:03d}"
            # Avoid trailing whitespace+digits; feed canonicalization strips those.
            name = f"TestBrand-{i + 1:03d}"
            category = categories[i % len(categories)]
            region = "Global"

            brand = models.Brand(
                id=brand_id,
                name=name,
                category=category,
                region=region,
                website=f"https://example.com/{brand_id}",
                description=f"{name} is a test fixture brand.",
            )
            db.add(brand)

            heat = 95.0 - (i * 0.5)
            risk = 25.0 + (i * 0.4)
            asym = 70.0 - (i * 0.2)
            cap_int = 45.0 + (i * 0.3)
            rev50 = 80.0 - (i * 0.9)
            rev10 = max(0.2, rev50 * 0.72)
            rev90 = rev50 * 1.32
            cap_req = max(1.0, rev50 * 0.12)

            db.add(
                models.Scorecard(
                    brand_id=brand_id,
                    snapshot_week=snapshot_week,
                    heat_score=heat,
                    risk_score=risk,
                    asymmetry_index=asym,
                    capital_intensity=cap_int,
                    revenue_p10=rev10,
                    revenue_p50=rev50,
                    revenue_p90=rev90,
                    delta_heat=0.0,
                    confidence=0.82,
                    confidence_reasons=["cross-source corroboration", "test fixture dataset"],
                    suggested_deal_structure="Minority growth investment",
                    capital_required_musd=cap_req,
                )
            )

            # Minimal evidence to support chat citations contract.
            db.add(
                models.EvidenceCitation(
                    brand_id=brand_id,
                    title=f"{name} source 1",
                    url=f"https://example.com/{brand_id}/source-1",
                    snippet="Test evidence snippet.",
                    source="test",
                    reliability=0.8,
                )
            )
            db.add(
                models.EvidenceCitation(
                    brand_id=brand_id,
                    title=f"{name} source 2",
                    url=f"https://example.com/{brand_id}/source-2",
                    snippet="Test evidence snippet.",
                    source="test",
                    reliability=0.8,
                )
            )

            # Minimal timeseries required for charts.
            db.add(
                models.TimeSeriesPoint(
                    brand_id=brand_id,
                    metric="heat",
                    observed_at=snapshot_week,
                    value=heat,
                    source="test",
                    reliability=0.8,
                )
            )

        db.commit()
    finally:
        db.close()

    with TestClient(app) as test_client:
        yield test_client


def test_feed_sorted_heat_desc(client: TestClient) -> None:
    res = client.get("/v1/feed", params={"sort": "heat", "limit": 25})
    assert res.status_code == 200
    payload = res.json()
    items = payload["items"]
    assert len(items) == 25

    heats = [row["heat_score"] for row in items]
    assert heats == sorted(heats, reverse=True)
    assert [row["rank"] for row in items] == list(range(1, 26))


def test_feed_sorted_capital_required_desc(client: TestClient) -> None:
    res = client.get("/v1/feed", params={"sort": "capital_required", "limit": 25})
    assert res.status_code == 200
    payload = res.json()
    items = payload["items"]
    assert len(items) == 25
    capitals = [row["capital_required_musd"] for row in items]
    assert capitals == sorted(capitals, reverse=True)


def test_feed_names_unique_in_ranked_view(client: TestClient) -> None:
    res = client.get("/v1/feed", params={"sort": "heat", "limit": 200})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) > 0
    names = [row["name"] for row in items]
    assert len(names) == len(set(names))
    canonical = [re.sub(r"\s+\d+$", "", row["name"].strip().lower()) for row in items]
    assert len(canonical) == len(set(canonical))


def test_discover_endpoint(client: TestClient) -> None:
    res = client.get("/v1/discover", params={"industry": "outdoor apparel", "region": "north america", "limit": 8})
    assert res.status_code == 200
    payload = res.json()
    assert payload["industry"] == "outdoor apparel"
    assert isinstance(payload["provider_attempts"], list)
    assert isinstance(payload["items"], list)
    assert "report" in payload
    assert payload["report"]["industry"] == "outdoor apparel"
    assert isinstance(payload["report"]["company_reports"], list)
    # Discovery is retrieval-dependent; tests only assert schema integrity.
    if payload["report"]["company_reports"]:
        top = payload["report"]["company_reports"][0]
        assert 0 <= top["fit_score"] <= 100
        assert 0 <= top["risk_score"] <= 100
        assert top["suggested_deal_structure"]
        assert len(top["operational_cost_down_actions"]) >= 3
        assert len(top["execution_plan_30_60_90"]) == 3


def test_brand_detail_and_timeseries(client: TestClient) -> None:
    feed = client.get("/v1/feed", params={"limit": 1}).json()
    brand_id = feed["items"][0]["brand_id"]

    detail = client.get(f"/v1/brand/{brand_id}")
    assert detail.status_code == 200
    detail_json = detail.json()
    assert detail_json["brand"]["id"] == brand_id
    assert detail_json["confidence"]["overall"] >= 0
    assert detail_json["production_snapshot"]["current_model"]
    assert len(detail_json["production_options"]) >= 3
    assert len(detail_json["cost_reduction_opportunities"]) >= 2
    assert len(detail_json["data_collection_snapshot"]["social_signals"]) >= 5
    assert len(detail_json["data_collection_snapshot"]["commerce_signals"]) >= 5
    assert len(detail_json["data_collection_snapshot"]["search_cultural_signals"]) >= 4
    assert detail_json["engagement_breakdown"]["comments_to_likes_ratio"] >= 0
    assert detail_json["financial_inference"]["gross_margin_estimate_pct"] >= 0
    assert detail_json["risk_scan"]["platform_dependency_risk"] in {"low", "medium", "high"}
    assert detail_json["deal_structuring"]["suggested_ownership_target_pct"]

    ts = client.get(f"/v1/brand/{brand_id}/timeseries")
    assert ts.status_code == 200
    assert len(ts.json()["points"]) > 0


def test_simulation_seed_reproducible(client: TestClient) -> None:
    feed = client.get("/v1/feed", params={"limit": 1}).json()
    brand_id = feed["items"][0]["brand_id"]

    body = {"brand_id": brand_id, "preset": "meta_cpm_spike", "iterations": 300, "seed": 11}
    a = client.post("/v1/simulate", json=body)
    b = client.post("/v1/simulate", json=body)
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json() == b.json()


def test_chat_has_citations(client: TestClient) -> None:
    feed = client.get("/v1/feed", params={"limit": 1}).json()
    brand_id = feed["items"][0]["brand_id"]

    body = {
        "brand_id": brand_id,
        "mode": "analysis",
        "messages": [{"role": "user", "content": "Summarize key diligence risks and production cost-down opportunities."}],
    }
    res = client.post("/v1/chat", json=body)
    assert res.status_code == 200
    payload = res.json()
    assert payload["answer"]
    assert isinstance(payload["citations"], list)


def test_chat_production_plan_mode(client: TestClient) -> None:
    feed = client.get("/v1/feed", params={"limit": 1}).json()
    brand_id = feed["items"][0]["brand_id"]

    body = {
        "brand_id": brand_id,
        "mode": "production_plan",
        "messages": [{"role": "user", "content": "Give me a cheaper production strategy."}],
    }
    res = client.post("/v1/chat", json=body)
    assert res.status_code == 200
    payload = res.json()
    assert payload["answer"]
    assert "30/60/90" in payload["answer"]
    assert isinstance(payload["citations"], list)


def test_report_generation_mentions_cost_down(client: TestClient) -> None:
    feed = client.get("/v1/feed", params={"limit": 1}).json()
    brand_id = feed["items"][0]["brand_id"]

    res = client.post("/v1/report", json={"brand_id": brand_id})
    assert res.status_code == 200
    payload = res.json()
    assert payload["path"].endswith(".pdf")
    assert "cost-down" in payload["summary"].lower()
    assert "data-collection snapshot" in payload["summary"].lower()


def test_top_report_batch_endpoint(client: TestClient) -> None:
    res = client.post("/v1/report/top", params={"limit": 2})
    assert res.status_code == 200
    payload = res.json()
    assert payload["count"] == 2
    assert len(payload["reports"]) == 2


def test_chat_guardrail_detection() -> None:
    svc = ChatService(Settings())
    assert svc._should_force_profile_grounding(
        "I cannot provide a specific analysis because there is no data about this brand."
    )
    assert not svc._should_force_profile_grounding(
        "Brand is strong on heat and has two actionable production options."
    )
