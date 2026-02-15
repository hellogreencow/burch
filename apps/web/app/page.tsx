"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../lib/api";
import {
  BrandProfile,
  BrandSummary,
  ChatMode,
  ChatMessage,
  ChatResponse,
  DiscoverResponse,
  ReportArtifact,
  ScenarioResult,
  TimeseriesResponse,
} from "../lib/types";

const SORT_OPTIONS = [
  { label: "Heat", value: "heat" },
  { label: "Asymmetry", value: "asymmetry" },
  { label: "Risk", value: "risk" },
  { label: "Revenue", value: "revenue" },
  { label: "Capital Required", value: "capital_required" },
] as const;

const SCENARIO_PRESETS = [
  { label: "Meta CPM Spike", value: "meta_cpm_spike" },
  { label: "TikTok Ban", value: "tiktok_ban" },
  { label: "Wholesale Contraction", value: "wholesale_contraction" },
] as const;

function formatMillions(value: number): string {
  return `$${value.toFixed(1)}M`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatDelta(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function Sparkline({ values, height = 92 }: { values: number[]; height?: number }) {
  if (!values.length) {
    return <div className="sparkline-empty">No signal data yet.</div>;
  }
  const width = 540;
  const chartHeight = height;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);

  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = chartHeight - ((value - min) / span) * chartHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${chartHeight}`}
      className="sparkline"
      preserveAspectRatio="none"
      style={{ height }}
    >
      <polyline points={points} fill="none" />
    </svg>
  );
}

export default function HomePage() {
  const [sort, setSort] = useState<(typeof SORT_OPTIONS)[number]["value"]>("heat");
  const [search, setSearch] = useState("");

  const [feed, setFeed] = useState<BrandSummary[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState<string | null>(null);
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesResponse | null>(null);

  const [preset, setPreset] = useState<(typeof SCENARIO_PRESETS)[number]["value"]>("meta_cpm_spike");
  const [simulation, setSimulation] = useState<ScenarioResult | null>(null);
  const [report, setReport] = useState<ReportArtifact | null>(null);
  const [reseedMessage, setReseedMessage] = useState<string | null>(null);
  const [reseeding, setReseeding] = useState(false);

  const [discoverData, setDiscoverData] = useState<DiscoverResponse | null>(null);
  const [discovering, setDiscovering] = useState(false);

  type DockMode = "chat" | "lab" | "discover";
  const [dockMode, setDockMode] = useState<DockMode>("chat");
  const [analystOpen, setAnalystOpen] = useState(false);

  const [chatMode, setChatMode] = useState<ChatMode>("analysis");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatMeta, setChatMeta] = useState<ChatResponse | null>(null);

  const [loadingFeed, setLoadingFeed] = useState(true);
  const [loadingBrand, setLoadingBrand] = useState(false);
  const [runningScenario, setRunningScenario] = useState(false);
  const [sendingChat, setSendingChat] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const liveTapeRef = useRef<HTMLElement>(null);
  const brandRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const timeout = setTimeout(async () => {
      setLoadingFeed(true);
      setError(null);
      try {
        const payload = await apiClient.getFeed(sort, search);
        setFeed(payload.items);
        if (!payload.items.length) {
          setSelectedBrandId(null);
          setProfile(null);
          setTimeseries(null);
          return;
        }

        if (!selectedBrandId || !payload.items.some((item) => item.brand_id === selectedBrandId)) {
          setSelectedBrandId(payload.items[0].brand_id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load feed.");
      } finally {
        setLoadingFeed(false);
      }
    }, 220);

    return () => clearTimeout(timeout);
  }, [sort, search, selectedBrandId]);

  useEffect(() => {
    if (!selectedBrandId) {
      return;
    }

    const run = async () => {
      setLoadingBrand(true);
      setError(null);
      try {
        const [profileRes, timeseriesRes] = await Promise.all([
          apiClient.getBrand(selectedBrandId),
          apiClient.getTimeseries(selectedBrandId),
        ]);
        setProfile(profileRes);
        setTimeseries(timeseriesRes);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load brand detail.");
      } finally {
        setLoadingBrand(false);
      }
    };

    void run();
  }, [selectedBrandId]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const targetTag = (event.target as HTMLElement)?.tagName?.toLowerCase();
      const inInput = targetTag === "input" || targetTag === "textarea";

      if (event.key === "Escape") {
        if (analystOpen) {
          event.preventDefault();
          setAnalystOpen(false);
        }
        return;
      }

      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (event.key.toLowerCase() === "c") {
        if (inInput) {
          return;
        }
        event.preventDefault();
        setDockMode("chat");
        setAnalystOpen((prev) => !prev);
        setTimeout(() => chatInputRef.current?.focus(), 0);
        return;
      }
      if (event.key === "1") {
        if (inInput) {
          return;
        }
        event.preventDefault();
        setDockMode("chat");
        setTimeout(() => chatInputRef.current?.focus(), 0);
        return;
      }
      if (event.key === "2") {
        if (inInput) {
          return;
        }
        event.preventDefault();
        setDockMode("lab");
        return;
      }
      if (event.key === "3") {
        if (inInput) {
          return;
        }
        event.preventDefault();
        setDockMode("discover");
        return;
      }
      if (event.key.toLowerCase() === "j" && feed.length > 0) {
        if (inInput) {
          return;
        }
        event.preventDefault();
        const idx = feed.findIndex((b) => b.brand_id === selectedBrandId);
        const next = feed[(idx + 1) % feed.length];
        setSelectedBrandId(next.brand_id);
      }
      if (event.key.toLowerCase() === "k" && feed.length > 0) {
        if (inInput) {
          return;
        }
        event.preventDefault();
        const idx = feed.findIndex((b) => b.brand_id === selectedBrandId);
        const prev = feed[(idx - 1 + feed.length) % feed.length];
        setSelectedBrandId(prev.brand_id);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [analystOpen, feed, selectedBrandId]);

  const heatSeries = useMemo(() => {
    if (!timeseries) {
      return [];
    }
    return timeseries.points.filter((p) => p.metric === "heat").map((p) => p.value);
  }, [timeseries]);

  const instagramSeries = useMemo(() => {
    if (!timeseries) {
      return [];
    }
    return timeseries.points.filter((p) => p.metric === "instagram_follower_velocity").map((p) => p.value);
  }, [timeseries]);

  const tiktokSeries = useMemo(() => {
    if (!timeseries) {
      return [];
    }
    return timeseries.points.filter((p) => p.metric === "tiktok_follower_velocity").map((p) => p.value);
  }, [timeseries]);

  const runScenario = async () => {
    if (!selectedBrandId) {
      return;
    }
    setDockMode("lab");
    setRunningScenario(true);
    setError(null);
    try {
      const result = await apiClient.runSimulation(selectedBrandId, preset, 42);
      setSimulation(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scenario run failed.");
    } finally {
      setRunningScenario(false);
    }
  };

  const exportReport = async () => {
    if (!selectedBrandId) {
      return;
    }
    setDockMode("lab");
    setError(null);
    try {
      const artifact = await apiClient.createReport(selectedBrandId);
      setReport(artifact);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report export failed.");
    }
  };

  const reseedUniverse = async () => {
    setReseeding(true);
    setError(null);
    setReseedMessage(null);
    try {
      const out = await apiClient.reseedUniverse(200, 30);
      setReseedMessage(`${out.message} Brands: ${out.brands}. Snapshots: ${out.snapshots}.`);
      const payload = await apiClient.getFeed(sort, search);
      setFeed(payload.items);
      if (payload.items.length > 0) {
        setSelectedBrandId(payload.items[0].brand_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reseed failed.");
    } finally {
      setReseeding(false);
    }
  };

  const runIndustryDiscovery = async (industryRaw: string) => {
    const industry = industryRaw.trim();
    if (!industry) {
      setError("Type an industry (e.g. outdoor apparel) and press Enter.");
      return;
    }
    setDockMode("discover");
    setDiscovering(true);
    setError(null);
    try {
      const data = await apiClient.discoverCompanies(industry, undefined, 14);
      setDiscoverData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Industry discovery failed.");
    } finally {
      setDiscovering(false);
    }
  };

  const sendChat = async (event: FormEvent) => {
    event.preventDefault();
    const content = chatInput.trim();
    if (!content) {
      return;
    }

    const nextMessages: ChatMessage[] = [...chatMessages, { role: "user", content }];
    setChatMessages(nextMessages);
    setChatInput("");
    setSendingChat(true);
    setError(null);

    try {
      const response = await apiClient.chat(selectedBrandId, nextMessages, chatMode);
      setChatMessages((prev) => [...prev, { role: "assistant", content: response.answer }]);
      setChatMeta(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat request failed.");
    } finally {
      setSendingChat(false);
    }
  };

  return (
    <main className="eidolon-shell">
      <header className="hero">
        <p className="hero-kicker">BURCH-EIDOLON / Global Consumer Signal Surface</p>
        <h1>Deal intelligence in one uninterrupted page.</h1>
        <p className="hero-subtext">
          Keyboard map: <kbd>/</kbd> search, <kbd>enter</kbd> map industry, <kbd>j</kbd>/<kbd>k</kbd> move brand focus, <kbd>c</kbd>{" "}
          toggle analyst.
        </p>

        <div className="command-strip" aria-label="Command controls">
          <input
            ref={searchRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void runIndustryDiscovery(search);
              }
            }}
            placeholder="Search brands (or press Enter to map an industry)..."
            aria-label="Global search"
          />
          <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)} aria-label="Sort mode">
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                Sort: {option.label}
              </option>
            ))}
          </select>
          <button type="button" onClick={reseedUniverse} disabled={reseeding}>
            {reseeding ? "Rebuilding..." : "Rebuild"}
          </button>
        </div>

        {reseedMessage ? <p className="status-line">{reseedMessage}</p> : null}
        {error ? <p className="error-line">{error}</p> : null}
      </header>

      <div className="workspace-shell">
        <section ref={liveTapeRef} className="panel" id="live-signal-tape">
          <h2>Live Signal Tape</h2>
          <div className="panel-scroll">
            {loadingFeed ? <p>Loading feed...</p> : null}
            {!loadingFeed && feed.length === 0 ? <p>No brands matched this query.</p> : null}

            {feed.length > 0 ? (
              <div className="ticker-wrap">
                <div className="ticker-track">
                  {feed.slice(0, 40).map((brand) => (
                    <span key={brand.brand_id}>
                      {brand.name} <em>{brand.heat_score.toFixed(1)}</em>{" "}
                      <strong>
                        {brand.delta_heat >= 0 ? "+" : ""}
                        {brand.delta_heat.toFixed(1)}
                      </strong>
                      {brand.deeper_analysis_required ? " ⬩deep" : ""}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <ol className="brand-list" aria-label="Ranked brands">
              {feed.slice(0, 120).map((brand) => {
                const active = brand.brand_id === selectedBrandId;
                return (
                  <li key={brand.brand_id}>
                    <button
                      type="button"
                      className={active ? "active" : ""}
                      onClick={() => setSelectedBrandId(brand.brand_id)}
                      aria-pressed={active}
                    >
                      <span>
                        #{brand.rank} {brand.name}
                      </span>
                      <small>
                        H {brand.heat_score.toFixed(1)} | A {brand.asymmetry_index.toFixed(1)} | R {brand.risk_score.toFixed(1)}
                      </small>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        <section ref={brandRef} className="panel" id="brand-focus">
          <h2>Brand Focus</h2>
          <div className="panel-scroll">
            <article className="brand-detail" aria-live="polite">
              {loadingBrand ? <p>Loading brand profile...</p> : null}
              {!loadingBrand && profile ? (
                <>
                  <p className="brand-meta">
                    {profile.brand.category} / {profile.brand.region}
                  </p>
                  <h3>{profile.brand.name}</h3>
                  <p>{profile.brand.description}</p>
                  <p>
                    <a href={profile.brand.website} target="_blank" rel="noreferrer">
                      {profile.brand.website}
                    </a>
                  </p>

                  <p className="metrics-line">
                    Heat {profile.scorecard.heat_score.toFixed(1)} · Risk {profile.scorecard.risk_score.toFixed(1)} · Asymmetry{" "}
                    {profile.scorecard.asymmetry_index.toFixed(1)} · Revenue {formatMillions(profile.scorecard.revenue_p50)} · Capital{" "}
                    {formatMillions(profile.scorecard.capital_required_musd)} · Confidence {(profile.confidence.overall * 100).toFixed(0)}%
                  </p>
                  {profile.scorecard.deeper_analysis_required ? (
                    <p className="deeper-flag">Heat {">="} 75: deeper analysis track is active for this brand.</p>
                  ) : null}

                  <div className="spark-grid" aria-label="Social growth charts">
                    <div className="spark-cell">
                      <p className="spark-label">Heat</p>
                      <Sparkline values={heatSeries} height={64} />
                    </div>
                    <div className="spark-cell">
                      <p className="spark-label">Instagram velocity</p>
                      <Sparkline values={instagramSeries} height={64} />
                    </div>
                    <div className="spark-cell">
                      <p className="spark-label">TikTok velocity</p>
                      <Sparkline values={tiktokSeries} height={64} />
                    </div>
                  </div>

                  <p className="memo-preview">{profile.memo_preview}</p>

                  <ul className="confidence-reasons">
                    {profile.confidence.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>

                  <h4>Production + Cost-Down</h4>
                  <p className="production-line">
                    Model: {profile.production_snapshot.current_model} · Unit economics pressure: {profile.production_snapshot.unit_economics_pressure} · Confidence{" "}
                    {(profile.production_snapshot.confidence * 100).toFixed(0)}%
                  </p>
                  <ul className="production-list">
                    {profile.production_options.slice(0, 3).map((option) => (
                      <li key={option.option_name}>
                        <strong>{option.option_name}</strong> {option.estimated_savings_pct.toFixed(1)}% savings, {option.time_to_impact_months}mo, {option.execution_risk} risk.
                      </li>
                    ))}
                  </ul>
                  <ul className="cost-op-list">
                    {profile.cost_reduction_opportunities.map((opportunity) => (
                      <li key={opportunity.title}>
                        {opportunity.title}: {opportunity.estimated_savings_pct_low.toFixed(1)}%-{opportunity.estimated_savings_pct_high.toFixed(1)}% ({opportunity.lever})
                      </li>
                    ))}
                  </ul>

                  <h4>Data Collection Layer</h4>
                  <p className="metrics-line">{profile.data_collection_snapshot.acceleration_priority_note}</p>
                  <section className="signal-snapshot">
                    <p className="signal-group-title">Social signals</p>
                    <ul className="mini-list">
                      {profile.data_collection_snapshot.social_signals.map((signal) => (
                        <li key={`social-${signal.metric}`}>
                          {signal.metric}: {signal.current.toFixed(2)} ({formatDelta(signal.delta_12w)} /12w) · {signal.source}
                        </li>
                      ))}
                    </ul>

                    <p className="signal-group-title">Commerce signals</p>
                    <ul className="mini-list">
                      {profile.data_collection_snapshot.commerce_signals.map((signal) => (
                        <li key={`commerce-${signal.metric}`}>
                          {signal.metric}: {signal.current.toFixed(2)} ({formatDelta(signal.delta_12w)} /12w) · {signal.source}
                        </li>
                      ))}
                    </ul>

                    <p className="signal-group-title">Search + cultural signals</p>
                    <ul className="mini-list">
                      {profile.data_collection_snapshot.search_cultural_signals.map((signal) => (
                        <li key={`search-${signal.metric}`}>
                          {signal.metric}: {signal.current.toFixed(2)} ({formatDelta(signal.delta_12w)} /12w) · {signal.source}
                        </li>
                      ))}
                    </ul>
                  </section>

                  <h4>Engagement Breakdown</h4>
                  <p className="metrics-line">
                    Comments/Likes {profile.engagement_breakdown.comments_to_likes_ratio.toFixed(3)} · Repeat density{" "}
                    {(profile.engagement_breakdown.repeat_commenter_density * 100).toFixed(1)}% · UGC {profile.engagement_breakdown.ugc_depth_score.toFixed(1)} · Sentiment{" "}
                    {profile.engagement_breakdown.sentiment_score.toFixed(1)}
                  </p>

                  <h4>Financial Inference Model</h4>
                  <p className="metrics-line">
                    Traffic {profile.financial_inference.traffic_estimate_kmo.toFixed(1)}k/mo · Conversion {formatPercent(profile.financial_inference.conversion_assumption_pct)} · AOV ${profile.financial_inference.average_order_value_usd.toFixed(2)} · Gross Margin {formatPercent(profile.financial_inference.gross_margin_estimate_pct)}
                  </p>
                  <p className="metrics-line">
                    CAC ${profile.financial_inference.cac_proxy_usd.toFixed(1)} · LTV ${profile.financial_inference.ltv_proxy_usd.toFixed(1)} · SKU {profile.financial_inference.sku_count_estimate} · Sell-through {formatPercent(profile.financial_inference.sell_through_assumption_pct)}
                  </p>
                  <ul className="confidence-reasons">
                    {profile.financial_inference.scenario_flags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>

                  <h4>Risk Scan Summary</h4>
                  <p className="metrics-line">
                    Trademark {profile.risk_scan.trademark_strength} · Registry {profile.risk_scan.corporate_registry_verified ? "verified" : "pending"} · Platform {profile.risk_scan.platform_dependency_risk} · Algorithm {profile.risk_scan.algorithm_exposure_risk}
                  </p>
                  <p className="metrics-line">
                    Supplier concentration {profile.risk_scan.supplier_concentration_risk} · Founder dependency {profile.risk_scan.founder_dependency_score.toFixed(1)}
                  </p>
                  <ul className="confidence-reasons">
                    {[...profile.risk_scan.litigation_flags, ...profile.risk_scan.key_risks].slice(0, 6).map((risk) => (
                      <li key={risk}>{risk}</li>
                    ))}
                  </ul>

                  <h4>Deal Structuring</h4>
                  <p className="metrics-line">
                    Strategy {profile.deal_structuring.suggested_entry_strategy} · Ownership target {profile.deal_structuring.suggested_ownership_target_pct} · Capital {formatMillions(profile.deal_structuring.estimated_capital_required_musd)}
                  </p>
                  <p>{profile.deal_structuring.founder_alignment_thesis}</p>
                  <pre className="outreach-email">{profile.deal_structuring.draft_outreach_email}</pre>

                  <h4>Evidence</h4>
                  <ul className="evidence-list">
                    {profile.evidence.slice(0, 8).map((citation) => (
                      <li key={`${citation.url}-${citation.title}`}>
                        <a href={citation.url} target="_blank" rel="noreferrer">
                          {citation.title}
                        </a>
                        <span>{citation.source}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </article>
          </div>
        </section>

        <section className="panel dock" id="dock">
          <div className="panel-head">
            <h2>Dock</h2>
            <nav className="dock-tabs" aria-label="Dock modes">
              <button
                type="button"
                className={dockMode === "chat" ? "active" : ""}
                onClick={() => setDockMode("chat")}
              >
                Analyst
              </button>
              <button
                type="button"
                className={dockMode === "lab" ? "active" : ""}
                onClick={() => setDockMode("lab")}
              >
                Lab
              </button>
              <button
                type="button"
                className={dockMode === "discover" ? "active" : ""}
                onClick={() => setDockMode("discover")}
              >
                Discover
              </button>
            </nav>
          </div>

          <div className="dock-body">
            {dockMode === "discover" ? (
              <div className="dock-scroll">
                {!discoverData ? (
                  <p>Type an industry in search and press Enter to generate a company map.</p>
                ) : (
                  <>
                    <p className="metrics-line">
                      Focus {discoverData.industry}
                      {discoverData.region ? ` · ${discoverData.region}` : ""} · Candidates {discoverData.report.company_reports.length}
                    </p>
                    <p className="memo-preview">{discoverData.report.narrative}</p>
                    {discoverData.report.top_signals.length ? (
                      <ul className="confidence-reasons">
                        {discoverData.report.top_signals.map((signal) => (
                          <li key={signal}>{signal}</li>
                        ))}
                      </ul>
                    ) : null}

                    <h4>Company Opportunity Reports</h4>
                    <ul className="company-report-list">
                      {discoverData.report.company_reports.map((company, index) => (
                        <li key={`${company.source_url}-${index}`}>
                          <details className="company-preview">
                            <summary>
                              <span>{company.name}</span>
                              <small>
                                Fit {company.fit_score.toFixed(1)} · Risk {company.risk_score.toFixed(1)} · Confidence{" "}
                                {(company.confidence * 100).toFixed(0)}%
                              </small>
                            </summary>
                            <div className="company-preview-body">
                              <p>
                                <a href={company.source_url} target="_blank" rel="noreferrer">
                                  Source
                                </a>{" "}
                                · {company.source}
                              </p>
                              <p className="metrics-line">
                                Momentum {company.momentum_score.toFixed(1)} · Asymmetry {company.asymmetry_score.toFixed(1)} · Revenue band{" "}
                                {company.estimated_revenue_band}
                              </p>
                              <p className="metrics-line">Suggested structure {company.suggested_deal_structure}</p>
                              <p>{company.opportunity_thesis}</p>
                              <p>{company.production_cost_down_angle}</p>
                              <p>{company.next_step}</p>

                              <h4>Cost-Down Actions</h4>
                              <ul className="mini-list">
                                {company.operational_cost_down_actions.map((action) => (
                                  <li key={action}>{action}</li>
                                ))}
                              </ul>

                              <h4>Execution Plan 30/60/90</h4>
                              <ul className="mini-list">
                                {company.execution_plan_30_60_90.map((item) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>

                              <h4>Key Risks</h4>
                              <ul className="mini-list">
                                {company.key_risks.map((risk) => (
                                  <li key={risk}>{risk}</li>
                                ))}
                              </ul>

                              <h4>Diligence Questions</h4>
                              <ul className="mini-list">
                                {company.diligence_questions.map((q) => (
                                  <li key={q}>{q}</li>
                                ))}
                              </ul>
                            </div>
                          </details>
                        </li>
                      ))}
                    </ul>

                    <details className="raw-discovery">
                      <summary>Raw discovery results</summary>
                      <ul className="discovery-list">
                        {discoverData.items.map((item, index) => (
                          <li key={`${item.url}-${index}`}>
                            <a href={item.url} target="_blank" rel="noreferrer">
                              {item.name_guess}
                            </a>
                            <small>{item.source}</small>
                            <p>{item.title}</p>
                            {item.snippet ? <p>{item.snippet}</p> : null}
                          </li>
                        ))}
                      </ul>
                    </details>

                    <details className="provider-trace">
                      <summary>Provider trace</summary>
                      <ul>
                        {discoverData.provider_attempts.map((attempt) => (
                          <li key={attempt}>{attempt}</li>
                        ))}
                      </ul>
                    </details>
                  </>
                )}
              </div>
            ) : null}

            {dockMode === "lab" ? (
              <div className="dock-scroll">
                <div className="lab-controls">
                  <select value={preset} onChange={(event) => setPreset(event.target.value as typeof preset)} aria-label="Scenario preset">
                    {SCENARIO_PRESETS.map((option) => (
                      <option key={option.value} value={option.value}>
                        Scenario: {option.label}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={runScenario} disabled={!selectedBrandId || runningScenario}>
                    {runningScenario ? "Running..." : "Run scenario"}
                  </button>
                  <button type="button" onClick={exportReport} disabled={!selectedBrandId}>
                    Export report
                  </button>
                </div>

                {simulation ? (
                  <div className="simulation-lines">
                    <p>
                      Revenue delta (%): P10 {simulation.outcomes.revenue_delta_pct.p10.toFixed(1)} | P50{" "}
                      {simulation.outcomes.revenue_delta_pct.p50.toFixed(1)} | P90 {simulation.outcomes.revenue_delta_pct.p90.toFixed(1)}
                    </p>
                    <p>
                      Margin delta (%): P10 {simulation.outcomes.margin_delta_pct.p10.toFixed(1)} | P50{" "}
                      {simulation.outcomes.margin_delta_pct.p50.toFixed(1)} | P90 {simulation.outcomes.margin_delta_pct.p90.toFixed(1)}
                    </p>
                    <p>Risk shift: +{simulation.outcomes.risk_shift.toFixed(1)} points</p>
                    <p>Seed locked at {simulation.seed} for reproducibility.</p>
                  </div>
                ) : (
                  <p>Run a scenario preset to project probabilistic stress outcomes for the selected brand.</p>
                )}

                {report ? (
                  <p className="report-line">
                    Report generated at {new Date(report.generated_at).toLocaleString()}: <code>{report.path}</code>
                  </p>
                ) : null}
              </div>
            ) : null}

            {dockMode === "chat" ? (
              <div className="chat-shell">
                <div className="chat-meta-row">
                  <select value={chatMode} onChange={(event) => setChatMode(event.target.value as typeof chatMode)}>
                    <option value="analysis">Mode: Analysis</option>
                    <option value="memo">Mode: Memo</option>
                    <option value="diligence">Mode: Diligence</option>
                    <option value="production_plan">Mode: Production Plan</option>
                  </select>
                  {chatMeta ? (
                    <p>
                      Model {chatMeta.model} · Confidence {(chatMeta.confidence * 100).toFixed(0)}%
                    </p>
                  ) : null}
                </div>

                <ul className="chat-log">
                  {chatMessages.length === 0 ? (
                    <li>
                      Ask for thesis quality, production options, cost-down levers, or switch to Production Plan mode for a 30/60/90 execution plan.
                    </li>
                  ) : null}
                  {chatMessages.map((msg, index) => (
                    <li key={`${msg.role}-${index}`}>
                      <strong>{msg.role}:</strong> {msg.content}
                    </li>
                  ))}
                </ul>

                <form
                  className="chat-form"
                  onSubmit={(event) => {
                    setDockMode("chat");
                    void sendChat(event);
                  }}
                >
                  <input
                    ref={chatInputRef}
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    placeholder="Ask BURCH-EIDOLON..."
                    aria-label="AI analyst overlay message"
                  />
                  <button type="submit" disabled={sendingChat}>
                    {sendingChat ? "Sending..." : "Send"}
                  </button>
                </form>

                {chatMeta?.citations?.length ? (
                  <ul className="chat-citations">
                    {chatMeta.citations.slice(0, 5).map((citation, index) => (
                      <li key={`${citation.url}-${index}`}>
                        <a href={citation.url} target="_blank" rel="noreferrer">
                          {citation.title}
                        </a>
                        <span>{citation.source}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {discovering ? <p className="status-line">Discovering companies...</p> : null}
          </div>
        </section>
      </div>

      {analystOpen ? (
        <div
          className="analyst-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="AI Analyst"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setAnalystOpen(false);
            }
          }}
        >
          <section className="analyst-panel">
            <header className="analyst-head">
              <div>
                <p className="analyst-kicker">AI Analyst</p>
                <p className="analyst-hint">
                  <kbd>esc</kbd> to close · <kbd>enter</kbd> to send
                </p>
              </div>
              {chatMeta ? (
                <p className="analyst-meta">
                  Model {chatMeta.model} · Confidence {(chatMeta.confidence * 100).toFixed(0)}%
                </p>
              ) : null}
            </header>

            <div className="analyst-body">
              <ul className="chat-log">
                {chatMessages.length === 0 ? (
                  <li>
                    Ask for thesis quality, production options, cost-down levers, or switch modes for memo/diligence.
                  </li>
                ) : null}
                {chatMessages.map((msg, index) => (
                  <li key={`overlay-${msg.role}-${index}`}>
                    <strong>{msg.role}:</strong> {msg.content}
                  </li>
                ))}
              </ul>

              <form
                className="chat-form"
                onSubmit={(event) => {
                  void sendChat(event);
                }}
              >
                <input
                  ref={chatInputRef}
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="Ask BURCH-EIDOLON..."
                  aria-label="AI analyst message"
                />
                <button type="submit" disabled={sendingChat}>
                  {sendingChat ? "Sending..." : "Send"}
                </button>
              </form>

              {chatMeta?.citations?.length ? (
                <ul className="chat-citations">
                  {chatMeta.citations.slice(0, 8).map((citation, index) => (
                    <li key={`overlay-${citation.url}-${index}`}>
                      <a href={citation.url} target="_blank" rel="noreferrer">
                        {citation.title}
                      </a>
                      <span>{citation.source}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
