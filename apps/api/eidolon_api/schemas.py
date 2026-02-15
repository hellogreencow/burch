from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


SortMode = Literal["heat", "asymmetry", "risk", "revenue", "capital_required"]


class EvidenceCitation(BaseModel):
    title: str
    url: str
    source: str
    snippet: str | None = None
    reliability: float | None = None


class ConfidenceEnvelope(BaseModel):
    overall: float = Field(..., ge=0, le=1)
    reasons: list[str]


class ScoreCard(BaseModel):
    snapshot_week: dt.date
    heat_score: float
    risk_score: float
    asymmetry_index: float
    capital_intensity: float
    revenue_p10: float
    revenue_p50: float
    revenue_p90: float
    delta_heat: float
    capital_required_musd: float
    suggested_deal_structure: str
    deeper_analysis_required: bool


class BrandSummary(BaseModel):
    rank: int
    brand_id: str
    name: str
    category: str
    region: str
    heat_score: float
    risk_score: float
    asymmetry_index: float
    capital_intensity: float
    revenue_p50: float
    capital_required_musd: float
    delta_heat: float
    confidence: float
    deeper_analysis_required: bool


class FeedResponse(BaseModel):
    generated_at: dt.datetime
    sort: SortMode
    items: list[BrandSummary]


class BrandData(BaseModel):
    id: str
    name: str
    category: str
    region: str
    website: str
    description: str


class ProductionSnapshot(BaseModel):
    current_model: str
    unit_economics_pressure: str
    bottlenecks: list[str]
    confidence: float = Field(..., ge=0, le=1)


class ProductionOption(BaseModel):
    option_name: str
    mode: str
    estimated_savings_pct: float = Field(..., ge=0, le=60)
    capex_impact_musd: float
    time_to_impact_months: int = Field(..., ge=1, le=48)
    execution_risk: Literal["low", "medium", "high"]
    rationale: str


class CostOpportunity(BaseModel):
    title: str
    lever: str
    estimated_savings_pct_low: float = Field(..., ge=0, le=60)
    estimated_savings_pct_high: float = Field(..., ge=0, le=60)
    confidence: float = Field(..., ge=0, le=1)
    rationale: str


class SignalPoint(BaseModel):
    metric: str
    current: float
    delta_12w: float
    source: str


class DataCollectionLayerSnapshot(BaseModel):
    social_signals: list[SignalPoint]
    commerce_signals: list[SignalPoint]
    search_cultural_signals: list[SignalPoint]
    acceleration_priority_note: str


class EngagementBreakdown(BaseModel):
    comments_to_likes_ratio: float = Field(..., ge=0, le=1)
    repeat_commenter_density: float = Field(..., ge=0, le=1)
    ugc_depth_score: float = Field(..., ge=0, le=100)
    sentiment_score: float = Field(..., ge=0, le=100)
    influencer_overlap_score: float = Field(..., ge=0, le=100)
    geographic_spread_score: float = Field(..., ge=0, le=100)


class FinancialInferenceModel(BaseModel):
    traffic_estimate_kmo: float = Field(..., ge=0)
    conversion_assumption_pct: float = Field(..., ge=0, le=100)
    average_order_value_usd: float = Field(..., ge=0)
    sku_count_estimate: int = Field(..., ge=1)
    sell_through_assumption_pct: float = Field(..., ge=0, le=100)
    gross_margin_estimate_pct: float = Field(..., ge=0, le=100)
    cac_proxy_usd: float = Field(..., ge=0)
    ltv_proxy_usd: float = Field(..., ge=0)
    scenario_flags: list[str]
    inference_notes: list[str]


class RiskScanSummary(BaseModel):
    trademark_strength: Literal["weak", "moderate", "strong"]
    corporate_registry_verified: bool
    litigation_flags: list[str]
    platform_dependency_risk: Literal["low", "medium", "high"]
    algorithm_exposure_risk: Literal["low", "medium", "high"]
    supplier_concentration_risk: Literal["low", "medium", "high"]
    founder_dependency_score: float = Field(..., ge=0, le=100)
    key_risks: list[str]


class DealStructuringPlan(BaseModel):
    suggested_entry_strategy: str
    suggested_ownership_target_pct: str
    estimated_capital_required_musd: float = Field(..., ge=0)
    founder_alignment_thesis: str
    draft_outreach_email: str
    deeper_analysis_required: bool


class BrandProfile(BaseModel):
    brand: BrandData
    scorecard: ScoreCard
    confidence: ConfidenceEnvelope
    evidence: list[EvidenceCitation]
    production_snapshot: ProductionSnapshot
    production_options: list[ProductionOption]
    cost_reduction_opportunities: list[CostOpportunity]
    data_collection_snapshot: DataCollectionLayerSnapshot
    engagement_breakdown: EngagementBreakdown
    financial_inference: FinancialInferenceModel
    risk_scan: RiskScanSummary
    deal_structuring: DealStructuringPlan
    memo_preview: str


class TimeSeriesPoint(BaseModel):
    metric: str
    observed_at: dt.date
    value: float
    source: str


class TimeSeriesResponse(BaseModel):
    brand_id: str
    points: list[TimeSeriesPoint]


class SimulateRequest(BaseModel):
    brand_id: str
    preset: Literal["meta_cpm_spike", "tiktok_ban", "wholesale_contraction"] = "meta_cpm_spike"
    iterations: int = Field(default=1000, ge=100, le=50000)
    seed: int = 42


class PercentileBand(BaseModel):
    p10: float
    p50: float
    p90: float


class ScenarioResult(BaseModel):
    brand_id: str
    preset: str
    seed: int
    outcomes: dict[str, PercentileBand | float]


class ReportRequest(BaseModel):
    brand_id: str


class ReportArtifact(BaseModel):
    brand_id: str
    generated_at: dt.datetime
    path: str
    summary: str


class ReportBatchArtifact(BaseModel):
    generated_at: dt.datetime
    count: int
    reports: list[ReportArtifact]


class DiscoveryCandidate(BaseModel):
    name_guess: str
    title: str
    url: str
    snippet: str
    source: str
    query: str


class DiscoveryCompanyReport(BaseModel):
    name: str
    source_url: str
    source: str
    fit_score: float = Field(..., ge=0, le=100)
    momentum_score: float = Field(..., ge=0, le=100)
    risk_score: float = Field(..., ge=0, le=100)
    asymmetry_score: float = Field(..., ge=0, le=100)
    estimated_revenue_band: str
    suggested_deal_structure: str
    production_cost_down_angle: str
    opportunity_thesis: str
    next_step: str
    key_risks: list[str]
    diligence_questions: list[str]
    operational_cost_down_actions: list[str]
    execution_plan_30_60_90: list[str]
    confidence: float = Field(..., ge=0, le=1)


class IndustryReport(BaseModel):
    industry: str
    region: str | None = None
    narrative: str
    top_signals: list[str]
    company_reports: list[DiscoveryCompanyReport]


class DiscoverResponse(BaseModel):
    generated_at: dt.datetime
    industry: str
    region: str | None = None
    provider_attempts: list[str]
    items: list[DiscoveryCandidate]
    report: IndustryReport


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    brand_id: str | None = None
    messages: list[ChatMessage]
    mode: Literal["analysis", "memo", "diligence", "production_plan"] = "analysis"


class ChatResponse(BaseModel):
    answer: str
    confidence: float = Field(..., ge=0, le=1)
    citations: list[EvidenceCitation]
    model: str
