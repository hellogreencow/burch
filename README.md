# BURCH-EIDOLON

One-page ethereal deal intelligence app with FastAPI backend, Next.js frontend, worker pipeline, and local Docker stack.

## Quick start

1. Start stack:
   ```bash
   ./run.sh
   ```
2. Open app:
   - Use the URLs printed by `run.sh` (random ports each run).
3. Stop stack:
   - Press `Ctrl+C` in the same terminal.

## Services

- `apps/web`: one-page Next.js UI
- `apps/api`: scoring, simulation, chat, report APIs
- `apps/worker`: ingestion and refresh jobs
- `packages/contracts`: shared JSON schemas
- `infra/searxng`: local SearXNG config

## Notes

- Paid search providers are disabled by default.
- Set `OPENROUTER_API_KEY` to enable live model-backed chat.
- Generated reports are written to `reports/generated/`.
- Brand outputs include production-option and cost-down opportunity intelligence aligned to the deal-flow workflow.
- AI chat includes `Production Plan` mode for a structured 30/60/90 cost-down execution strategy.
- `run.sh` reads `OPENROUTER_API_KEY` from `.env` (or from environment variable on first bootstrap).
- `run.sh` assigns random free host ports for web and API on every start.
- `run.sh` auto-opens the web app in your browser once it is reachable.
- Use `POST /v1/admin/reseed` to regenerate a clean unique-name demo universe.
- Use `POST /v1/report/top?limit=20` to auto-generate deep reports for the current top-ranked brands.
- Brand profiles now expose explicit PDF-aligned sections: engagement breakdown, financial inference model, risk scan summary, and structured outreach draft.
- Use `GET /v1/discover?industry=<focus>&region=<optional>&limit=12` to run low-cost industry-focused company discovery via provider routing.
- Discovery now returns an `Industry Report` with ranked company briefs (fit, momentum, risk, asymmetry, structure, cost-down angle, next step).
- The web header includes `Find companies` and `Reseed universe` controls, and renders company opportunity reports inline.
