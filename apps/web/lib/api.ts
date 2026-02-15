import {
  BrandProfile,
  ChatMode,
  ChatMessage,
  ChatResponse,
  DiscoverResponse,
  FeedResponse,
  ReportArtifact,
  ScenarioResult,
  TimeseriesResponse,
} from "./types";

// Always use same-origin; Next.js rewrites proxy /v1/* to the API container.
// This avoids CORS and avoids accidentally calling other local services on :8000.
const API_BASE = "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const apiClient = {
  getFeed(sort: string, search: string) {
    const params = new URLSearchParams({ sort, limit: "200" });
    if (search.trim()) {
      params.set("search", search.trim());
    }
    return api<FeedResponse>(`/v1/feed?${params.toString()}`);
  },
  discoverCompanies(industry: string, region?: string, limit = 12) {
    const params = new URLSearchParams({ industry: industry.trim(), limit: String(limit) });
    if (region && region.trim()) {
      params.set("region", region.trim());
    }
    return api<DiscoverResponse>(`/v1/discover?${params.toString()}`);
  },
  getBrand(brandId: string) {
    return api<BrandProfile>(`/v1/brand/${brandId}`);
  },
  getTimeseries(brandId: string) {
    return api<TimeseriesResponse>(`/v1/brand/${brandId}/timeseries`);
  },
  runSimulation(brandId: string, preset: string, seed = 42) {
    return api<ScenarioResult>(`/v1/simulate`, {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId, preset, seed, iterations: 1200 }),
    });
  },
  createReport(brandId: string) {
    return api<ReportArtifact>(`/v1/report`, {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId }),
    });
  },
  reseedUniverse(targetBrands = 200, enrichTopN = 30) {
    const params = new URLSearchParams({
      target_brands: String(targetBrands),
      enrich_top_n: String(enrichTopN),
    });
    return api<{ status: string; message: string; brands: number; created: number; updated: number; snapshots: number }>(
      `/v1/admin/reseed?${params.toString()}`,
      { method: "POST" },
    );
  },
  chat(brandId: string | null, messages: ChatMessage[], mode: ChatMode) {
    return api<ChatResponse>(`/v1/chat`, {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId, messages, mode }),
    });
  },
};
