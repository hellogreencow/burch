export type BrandSummary = {
  rank: number;
  brand_id: string;
  name: string;
  category: string;
  region: string;
  heat_score: number;
  risk_score: number;
  asymmetry_index: number;
  capital_intensity: number;
  revenue_p50: number;
  capital_required_musd: number;
  delta_heat: number;
  confidence: number;
  deeper_analysis_required: boolean;
};

export type FeedResponse = {
  generated_at: string;
  sort: "heat" | "asymmetry" | "risk" | "revenue" | "capital_required";
  items: BrandSummary[];
};

export type DiscoverResponse = {
  generated_at: string;
  industry: string;
  region?: string | null;
  provider_attempts: string[];
  items: Array<{
    name_guess: string;
    title: string;
    url: string;
    snippet: string;
    source: string;
    query: string;
  }>;
  report: {
    industry: string;
    region?: string | null;
    narrative: string;
    top_signals: string[];
    company_reports: Array<{
      name: string;
      source_url: string;
      source: string;
      fit_score: number;
      momentum_score: number;
      risk_score: number;
      asymmetry_score: number;
      estimated_revenue_band: string;
      suggested_deal_structure: string;
      production_cost_down_angle: string;
      opportunity_thesis: string;
      next_step: string;
      key_risks: string[];
      diligence_questions: string[];
      operational_cost_down_actions: string[];
      execution_plan_30_60_90: string[];
      confidence: number;
    }>;
  };
};

export type EvidenceCitation = {
  title: string;
  url: string;
  source: string;
  snippet?: string;
  reliability?: number;
};

export type BrandProfile = {
  brand: {
    id: string;
    name: string;
    category: string;
    region: string;
    website: string;
    description: string;
  };
  scorecard: {
    snapshot_week: string;
    heat_score: number;
    risk_score: number;
    asymmetry_index: number;
    capital_intensity: number;
    revenue_p10: number;
    revenue_p50: number;
    revenue_p90: number;
    delta_heat: number;
    capital_required_musd: number;
    suggested_deal_structure: string;
    deeper_analysis_required: boolean;
  };
  confidence: {
    overall: number;
    reasons: string[];
  };
  evidence: EvidenceCitation[];
  production_snapshot: {
    current_model: string;
    unit_economics_pressure: string;
    bottlenecks: string[];
    confidence: number;
  };
  production_options: Array<{
    option_name: string;
    mode: string;
    estimated_savings_pct: number;
    capex_impact_musd: number;
    time_to_impact_months: number;
    execution_risk: "low" | "medium" | "high";
    rationale: string;
  }>;
  cost_reduction_opportunities: Array<{
    title: string;
    lever: string;
    estimated_savings_pct_low: number;
    estimated_savings_pct_high: number;
    confidence: number;
    rationale: string;
  }>;
  data_collection_snapshot: {
    social_signals: Array<{ metric: string; current: number; delta_12w: number; source: string }>;
    commerce_signals: Array<{ metric: string; current: number; delta_12w: number; source: string }>;
    search_cultural_signals: Array<{ metric: string; current: number; delta_12w: number; source: string }>;
    acceleration_priority_note: string;
  };
  engagement_breakdown: {
    comments_to_likes_ratio: number;
    repeat_commenter_density: number;
    ugc_depth_score: number;
    sentiment_score: number;
    influencer_overlap_score: number;
    geographic_spread_score: number;
  };
  financial_inference: {
    traffic_estimate_kmo: number;
    conversion_assumption_pct: number;
    average_order_value_usd: number;
    sku_count_estimate: number;
    sell_through_assumption_pct: number;
    gross_margin_estimate_pct: number;
    cac_proxy_usd: number;
    ltv_proxy_usd: number;
    scenario_flags: string[];
    inference_notes: string[];
  };
  risk_scan: {
    trademark_strength: "weak" | "moderate" | "strong";
    corporate_registry_verified: boolean;
    litigation_flags: string[];
    platform_dependency_risk: "low" | "medium" | "high";
    algorithm_exposure_risk: "low" | "medium" | "high";
    supplier_concentration_risk: "low" | "medium" | "high";
    founder_dependency_score: number;
    key_risks: string[];
  };
  deal_structuring: {
    suggested_entry_strategy: string;
    suggested_ownership_target_pct: string;
    estimated_capital_required_musd: number;
    founder_alignment_thesis: string;
    draft_outreach_email: string;
    deeper_analysis_required: boolean;
  };
  memo_preview: string;
};

export type TimeseriesResponse = {
  brand_id: string;
  points: Array<{
    metric: string;
    observed_at: string;
    value: number;
    source: string;
  }>;
};

export type ScenarioResult = {
  brand_id: string;
  preset: string;
  seed: number;
  outcomes: {
    revenue_delta_pct: { p10: number; p50: number; p90: number };
    margin_delta_pct: { p10: number; p50: number; p90: number };
    risk_shift: number;
  };
};

export type ChatMessage = { role: "user" | "assistant" | "system"; content: string };
export type ChatMode = "analysis" | "memo" | "diligence" | "production_plan";

export type ChatResponse = {
  answer: string;
  confidence: number;
  citations: EvidenceCitation[];
  model: string;
};

export type ReportArtifact = {
  brand_id: string;
  generated_at: string;
  path: string;
  summary: string;
};
