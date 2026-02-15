from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    # Used to collapse duplicate entity rows caused by multiple domains / title variants.
    entity_key: Mapped[str] = mapped_column(String(140), index=True, default="")
    category: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(120), index=True)
    website: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)

    scorecards: Mapped[list[Scorecard]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    timeseries_points: Mapped[list[TimeSeriesPoint]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    evidence_items: Mapped[list[EvidenceCitation]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    reports: Mapped[list[GeneratedReport]] = relationship(back_populates="brand", cascade="all, delete-orphan")


class Scorecard(Base):
    __tablename__ = "scorecards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[str] = mapped_column(String(64), ForeignKey("brands.id"), index=True)
    snapshot_week: Mapped[dt.date] = mapped_column(Date, index=True)

    heat_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    asymmetry_index: Mapped[float] = mapped_column(Float)
    capital_intensity: Mapped[float] = mapped_column(Float)

    revenue_p10: Mapped[float] = mapped_column(Float)
    revenue_p50: Mapped[float] = mapped_column(Float)
    revenue_p90: Mapped[float] = mapped_column(Float)

    delta_heat: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_reasons: Mapped[list[str]] = mapped_column(JSON)

    suggested_deal_structure: Mapped[str] = mapped_column(String(120))
    capital_required_musd: Mapped[float] = mapped_column(Float)

    brand: Mapped[Brand] = relationship(back_populates="scorecards")


class TimeSeriesPoint(Base):
    __tablename__ = "timeseries_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[str] = mapped_column(String(64), ForeignKey("brands.id"), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[dt.date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(120))
    reliability: Mapped[float] = mapped_column(Float)

    brand: Mapped[Brand] = relationship(back_populates="timeseries_points")


class EvidenceCitation(Base):
    __tablename__ = "evidence_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[str] = mapped_column(String(64), ForeignKey("brands.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    snippet: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120))
    reliability: Mapped[float] = mapped_column(Float)

    brand: Mapped[Brand] = relationship(back_populates="evidence_items")


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[str] = mapped_column(String(64), ForeignKey("brands.id"), index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC), index=True)
    path: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)

    brand: Mapped[Brand] = relationship(back_populates="reports")
