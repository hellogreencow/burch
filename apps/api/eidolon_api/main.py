from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_db, init_db
from .schemas import (
    ChatRequest,
    ChatResponse,
    DiscoverResponse,
    FeedResponse,
    ReportArtifact,
    ReportBatchArtifact,
    ReportRequest,
    ScenarioResult,
    SimulateRequest,
)
from .services.chat import ChatService
from .services.discovery import discover_companies
from .services.ingestion import _legacy_synthetic_present, refresh_universe_snapshot, reseed_universe, reset_all_data
from .services.providers.router import SourceRouter
from .services.reporting import ReportService
from .services.scoring import build_brand_profile, build_feed, get_timeseries
from .services.simulation import run_simulation

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        # Keep runtime "no fake" by automatically wiping older synthetic PoC datasets if detected.
        if _legacy_synthetic_present(db):
            reset_all_data(db)
        yield
    finally:
        db.close()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = SourceRouter(settings=settings)
report_service = ReportService(reports_dir=settings.reports_dir)
chat_service = ChatService(settings=settings)


@app.get("/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "budget": router.budget_snapshot(),
        "searxng_base_url": settings.searxng_base_url,
    }


@app.get("/v1/feed", response_model=FeedResponse)
def feed(
    sort: str = Query(default="heat", pattern="^(heat|asymmetry|risk|revenue|capital_required)$"),
    limit: int = Query(default=200, ge=1, le=200),
    time_window: str = Query(default="12w", pattern="^(4w|12w|52w)$"),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> FeedResponse:
    try:
        return build_feed(db=db, sort=sort, limit=limit, search=search, time_window=time_window)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/discover", response_model=DiscoverResponse)
def discover(
    industry: str = Query(..., min_length=2, max_length=120),
    region: str | None = Query(default=None, min_length=2, max_length=120),
    limit: int = Query(default=12, ge=1, le=50),
) -> DiscoverResponse:
    try:
        return discover_companies(router=router, industry=industry, region=region, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/brand/{brand_id}")
def brand_detail(brand_id: str, db: Session = Depends(get_db)):
    try:
        return build_brand_profile(db=db, brand_id=brand_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/brand/{brand_id}/timeseries")
def brand_timeseries(brand_id: str, db: Session = Depends(get_db)):
    return get_timeseries(db=db, brand_id=brand_id)


@app.post("/v1/simulate", response_model=ScenarioResult)
def simulate(req: SimulateRequest) -> ScenarioResult:
    return run_simulation(req)


@app.post("/v1/report", response_model=ReportArtifact)
def report(req: ReportRequest, db: Session = Depends(get_db)) -> ReportArtifact:
    try:
        return report_service.generate(db=db, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/report/top", response_model=ReportBatchArtifact)
def report_top(
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> ReportBatchArtifact:
    artifacts = report_service.generate_top_ranked(db=db, limit=limit)
    return ReportBatchArtifact(
        generated_at=dt.datetime.now(dt.UTC),
        count=len(artifacts),
        reports=artifacts,
    )


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        return chat_service.chat(db=db, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/admin/refresh")
def refresh(
    target_brands: int = Query(default=200, ge=20, le=500),
    enrich_top_n: int = Query(default=30, ge=0, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = refresh_universe_snapshot(db=db, router=router, target_brands=target_brands, enrich_top_n=enrich_top_n)
    return {"status": "ok", "message": "Universe refreshed.", **result}


@app.post("/v1/admin/reseed")
def reseed(
    target_brands: int = Query(default=200, ge=20, le=500),
    enrich_top_n: int = Query(default=30, ge=0, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = reseed_universe(db=db, router=router, target_brands=target_brands, enrich_top_n=enrich_top_n)
    return {"status": "ok", "message": "Universe rebuilt.", **result}
