import { expect, Page, test } from "@playwright/test";

async function waitForFeed(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "Live Signal Tape" })).toBeVisible();
  const ensure = async () => {
    try {
      await page.request.post("/v1/admin/refresh?target_brands=60&enrich_top_n=20");
    } catch {
      // ignore; feed polling will fail if universe cannot be built
    }
  };

  if ((await page.locator(".brand-list li").count()) === 0) {
    await ensure();
  }

  await expect.poll(async () => page.locator(".brand-list li").count(), { timeout: 90_000 }).toBeGreaterThan(0);
}

function parseBrandName(label: string): string {
  return label.replace(/^#\d+\s+/, "").trim();
}

test.describe("BURCH-EIDOLON one-page feature suite", () => {
  test("renders full-page shell and all primary sections", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    await expect(page.getByRole("heading", { name: "Live Signal Tape" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Brand Focus" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dock" })).toBeVisible();
    const tabs = page.locator(".dock-tabs");
    await expect(tabs.getByRole("button", { name: "Analyst", exact: true })).toBeVisible();
    await expect(tabs.getByRole("button", { name: "Lab", exact: true })).toBeVisible();
    await expect(tabs.getByRole("button", { name: "Discover", exact: true })).toBeVisible();

    const pageScroll = await page.evaluate(() => ({
      height: document.documentElement.scrollHeight,
      viewport: window.innerHeight,
    }));
    expect(pageScroll.height).toBeLessThanOrEqual(pageScroll.viewport + 8);
  });

  test("keyboard controls work: /, c, j, k", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    const activeBrand = page.locator(".brand-list button.active span");
    const firstActive = await activeBrand.textContent();
    expect(firstActive).not.toBeNull();

    await page.keyboard.press("j");
    await expect(activeBrand).not.toHaveText(firstActive ?? "");

    await page.keyboard.press("k");
    await expect(activeBrand).toHaveText(firstActive ?? "");

    await page.keyboard.press("/");
    await expect(page.getByLabel("Global search")).toBeFocused();

    await page.getByRole("heading", { name: "Deal intelligence in one uninterrupted page." }).click();
    await page.keyboard.press("c");
    await expect(page.getByLabel("AI analyst message")).toBeFocused();
  });

  test("feed controls drive API query state and search filter", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    const sortSelect = page.getByLabel("Sort mode");
    const searchInput = page.getByLabel("Global search");

    const sortReqPromise = page.waitForRequest((req) => {
      const url = new URL(req.url());
      return url.pathname === "/v1/feed" && url.searchParams.get("sort") === "risk";
    });
    await sortSelect.selectOption("risk");
    await sortReqPromise;

    const firstLabel = (await page.locator(".brand-list button span").first().textContent()) ?? "";
    const term = parseBrandName(firstLabel).split(" ")[0];
    expect(term.length).toBeGreaterThan(0);

    const searchReqPromise = page.waitForRequest((req) => {
      const url = new URL(req.url());
      const search = url.searchParams.get("search");
      return url.pathname === "/v1/feed" && typeof search === "string" && search.toLowerCase() === term.toLowerCase();
    });
    await searchInput.fill(term);
    await searchReqPromise;

    await expect(page.locator(".brand-list button span").first()).toContainText(term, { ignoreCase: true });
  });

  test("brand focus shows deep PDF-aligned analysis sections", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    await expect(page.getByRole("heading", { name: "Data Collection Layer" })).toBeVisible();
    await expect(page.getByText("Social signals", { exact: true })).toBeVisible();
    await expect(page.getByText("Commerce signals", { exact: true })).toBeVisible();
    await expect(page.getByText("Search + cultural signals", { exact: true })).toBeVisible();

    await expect(page.getByRole("heading", { name: "Engagement Breakdown" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Financial Inference Model" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Risk Scan Summary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Deal Structuring" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();

    await expect.poll(async () => page.locator(".evidence-list li").count()).toBeGreaterThan(0);
  });

  test("industry discovery returns report output and expandable company detail", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    const searchInput = page.getByLabel("Global search");
    await searchInput.fill("outdoor apparel");
    await searchInput.press("Enter");
    await page.locator(".dock-tabs").getByRole("button", { name: "Discover", exact: true }).click();

    await expect(page.getByText(/focus outdoor apparel/i)).toBeVisible();

    const previewCount = await page.locator(".company-preview").count();
    if (previewCount > 0) {
      await page.locator(".company-preview summary").first().click();
      const body = page.locator(".company-preview-body").first();
      await expect(body.getByRole("heading", { name: "Cost-Down Actions" })).toBeVisible();
      await expect(body.getByRole("heading", { name: "Execution Plan 30/60/90" })).toBeVisible();
      await expect(body.getByRole("heading", { name: "Key Risks" })).toBeVisible();
      await expect(body.getByRole("heading", { name: "Diligence Questions" })).toBeVisible();
    }
  });

  test("simulation and report export execute successfully", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    await page.locator(".dock-tabs").getByRole("button", { name: "Lab", exact: true }).click();
    await page.getByRole("button", { name: "Run scenario" }).click();
    await expect(page.getByText("Seed locked at 42 for reproducibility.")).toBeVisible();

    await page.getByRole("button", { name: "Export report" }).click();
    await expect(page.locator(".report-line code")).toContainText(".pdf");
  });

  test("AI analyst returns answer and citations", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    await page.locator(".dock-tabs").getByRole("button", { name: "Analyst", exact: true }).click();
    const input = page.getByLabel("AI analyst message");
    await input.fill("Give me diligence risks and cheaper production options.");
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.locator(".chat-log li strong").last()).toHaveText(/assistant:/i);
    await expect.poll(async () => page.locator(".chat-citations li").count()).toBeGreaterThan(0);
  });

  test("universe refresh produces unique ranked names", async ({ page }) => {
    await page.goto("/");
    await waitForFeed(page);

    await page.request.post("/v1/admin/refresh?target_brands=80&enrich_top_n=25");

    const uniqueness = await page.evaluate(async () => {
      const res = await fetch("/v1/feed?sort=heat&limit=200");
      const payload = (await res.json()) as {
        items: Array<{ name: string; rank: number }>;
      };
      const names = payload.items.map((item) => item.name);
      const ranks = payload.items.map((item) => item.rank);
      return {
        count: names.length,
        unique: new Set(names).size,
        rankSequential: ranks.every((rank, idx) => rank === idx + 1),
      };
    });

    expect(uniqueness.count).toBeGreaterThan(0);
    expect(uniqueness.unique).toBe(uniqueness.count);
    expect(uniqueness.rankSequential).toBeTruthy();
  });

  test("API contract coverage for core endpoints", async ({ request }) => {
    await request.post("/v1/admin/refresh?target_brands=60&enrich_top_n=20");

    const feedRes = await request.get("/v1/feed?sort=heat&limit=200");
    expect(feedRes.ok()).toBeTruthy();
    const feedPayload = (await feedRes.json()) as {
      items: Array<{ brand_id: string; name: string; rank: number }>;
    };
    expect(feedPayload.items.length).toBeGreaterThan(0);
    expect(new Set(feedPayload.items.map((it) => it.name)).size).toBe(feedPayload.items.length);
    expect(feedPayload.items.every((it, idx) => it.rank === idx + 1)).toBeTruthy();

    const brandId = feedPayload.items[0].brand_id;

    const detailRes = await request.get(`/v1/brand/${brandId}`);
    expect(detailRes.ok()).toBeTruthy();
    const detailPayload = (await detailRes.json()) as {
      data_collection_snapshot: {
        social_signals: unknown[];
        commerce_signals: unknown[];
        search_cultural_signals: unknown[];
      };
    };
    expect(detailPayload.data_collection_snapshot.social_signals.length).toBeGreaterThanOrEqual(5);
    expect(detailPayload.data_collection_snapshot.commerce_signals.length).toBeGreaterThanOrEqual(5);
    expect(detailPayload.data_collection_snapshot.search_cultural_signals.length).toBeGreaterThanOrEqual(4);

    const timeseriesRes = await request.get(`/v1/brand/${brandId}/timeseries`);
    expect(timeseriesRes.ok()).toBeTruthy();

    const simRes = await request.post("/v1/simulate", {
      data: { brand_id: brandId, preset: "meta_cpm_spike", iterations: 300, seed: 42 },
    });
    expect(simRes.ok()).toBeTruthy();

    const reportRes = await request.post("/v1/report", { data: { brand_id: brandId } });
    expect(reportRes.ok()).toBeTruthy();
    const reportPayload = (await reportRes.json()) as { summary: string };
    expect(reportPayload.summary.toLowerCase()).toContain("cost-down");
    expect(reportPayload.summary.toLowerCase()).toContain("data-collection snapshot");

    const discoverRes = await request.get("/v1/discover?industry=outdoor%20apparel&limit=8");
    expect(discoverRes.ok()).toBeTruthy();
    const discoverPayload = (await discoverRes.json()) as {
      report: { company_reports: unknown[] };
    };
    expect(Array.isArray(discoverPayload.report.company_reports)).toBeTruthy();

    const chatRes = await request.post("/v1/chat", {
      data: {
        brand_id: brandId,
        mode: "analysis",
        messages: [{ role: "user", content: "Summarize risks and cost-down opportunities." }],
      },
    });
    expect(chatRes.ok()).toBeTruthy();
    const chatPayload = (await chatRes.json()) as { answer: string; citations: unknown[] };
    expect(chatPayload.answer.length).toBeGreaterThan(0);
    expect(Array.isArray(chatPayload.citations)).toBeTruthy();
  });

  test("mobile viewport smoke test", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await waitForFeed(page);

    await expect(page.getByRole("heading", { name: "Deal intelligence in one uninterrupted page." })).toBeVisible();
    await expect(page.getByLabel("Global search")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dock" })).toBeVisible();
    await page.locator(".dock-tabs").getByRole("button", { name: "Analyst", exact: true }).click();
    await expect(page.getByLabel("AI analyst message")).toBeVisible();
  });
});
