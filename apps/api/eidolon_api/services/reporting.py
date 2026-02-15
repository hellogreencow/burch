from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from .. import models, schemas
from .scoring import build_brand_profile, build_feed


class ReportService:
    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _record_generated_report(
        self,
        db: Session,
        brand_id: str,
        path: str,
        summary: str,
    ) -> None:
        db.add(
            models.GeneratedReport(
                brand_id=brand_id,
                path=path,
                summary=summary,
            )
        )
        db.commit()

    def generate(self, db: Session, req: schemas.ReportRequest) -> schemas.ReportArtifact:
        profile = build_brand_profile(db, req.brand_id)
        timestamp = dt.datetime.now(dt.UTC)

        filename = f"{profile.brand.id}_{timestamp.strftime('%Y%m%dT%H%M%SZ')}.pdf"
        output_path = self.reports_dir / filename

        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        body: list = []

        body.append(Paragraph(f"BURCH-EIDOLON Investment Brief: {profile.brand.name}", styles["Title"]))
        body.append(Spacer(1, 12))

        body.append(Paragraph("Executive Snapshot", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Category: {profile.brand.category}<br/>"
                    f"Region: {profile.brand.region}<br/>"
                    f"Heat: {profile.scorecard.heat_score:.1f} | Risk: {profile.scorecard.risk_score:.1f} | "
                    f"Asymmetry: {profile.scorecard.asymmetry_index:.1f}<br/>"
                    f"Revenue (P10/P50/P90): ${profile.scorecard.revenue_p10:.1f}M / "
                    f"${profile.scorecard.revenue_p50:.1f}M / ${profile.scorecard.revenue_p90:.1f}M<br/>"
                    f"Capital required: ${profile.scorecard.capital_required_musd:.1f}M<br/>"
                    f"Deeper analysis trigger (Heat >= 75): {'ON' if profile.scorecard.deeper_analysis_required else 'OFF'}"
                ),
                styles["BodyText"],
            )
        )
        body.append(Spacer(1, 12))

        body.append(Paragraph("Investment Thesis", styles["Heading2"]))
        body.append(Paragraph(profile.memo_preview, styles["BodyText"]))
        body.append(Spacer(1, 12))

        body.append(Paragraph("Deal Structuring Engine", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Suggested entry strategy: {profile.deal_structuring.suggested_entry_strategy}<br/>"
                    f"Suggested ownership target: {profile.deal_structuring.suggested_ownership_target_pct}<br/>"
                    f"Estimated capital required: ${profile.deal_structuring.estimated_capital_required_musd:.1f}M"
                ),
                styles["BodyText"],
            )
        )
        body.append(Spacer(1, 8))
        body.append(Paragraph(profile.deal_structuring.founder_alignment_thesis, styles["BodyText"]))
        body.append(Spacer(1, 12))

        body.append(Paragraph("Production Options + Cost-Down Plan", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Current production model: {profile.production_snapshot.current_model}<br/>"
                    f"Unit economics pressure: {profile.production_snapshot.unit_economics_pressure}<br/>"
                    f"Primary bottleneck: {profile.production_snapshot.bottlenecks[0]}"
                ),
                styles["BodyText"],
            )
        )
        body.append(Spacer(1, 8))
        for option in profile.production_options[:3]:
            body.append(
                Paragraph(
                    (
                        f"- {option.option_name}: est. savings {option.estimated_savings_pct:.1f}% | "
                        f"capex delta ${option.capex_impact_musd:.1f}M | "
                        f"time-to-impact {option.time_to_impact_months} months | risk {option.execution_risk}"
                    ),
                    styles["BodyText"],
                )
            )
        body.append(Spacer(1, 8))
        for opp in profile.cost_reduction_opportunities[:3]:
            body.append(
                Paragraph(
                    (
                        f"- {opp.title}: {opp.estimated_savings_pct_low:.1f}% to "
                        f"{opp.estimated_savings_pct_high:.1f}% potential savings "
                        f"({opp.lever}, confidence {opp.confidence:.2f})"
                    ),
                    styles["BodyText"],
                )
            )

        # Keep memo format as a consistent two-page artifact.
        body.append(PageBreak())

        body.append(Paragraph("Data Collection Layer Snapshot", styles["Heading2"]))
        body.append(Paragraph(profile.data_collection_snapshot.acceleration_priority_note, styles["BodyText"]))
        body.append(Spacer(1, 6))
        signal_groups = [
            ("Social Signals", profile.data_collection_snapshot.social_signals),
            ("Commerce Signals", profile.data_collection_snapshot.commerce_signals),
            ("Search + Cultural Signals", profile.data_collection_snapshot.search_cultural_signals),
        ]
        for title, signals in signal_groups:
            body.append(Paragraph(title, styles["Heading3"]))
            for signal in signals:
                delta_prefix = "+" if signal.delta_12w >= 0 else ""
                body.append(
                    Paragraph(
                        (
                            f"- {signal.metric}: {signal.current:.3f} "
                            f"({delta_prefix}{signal.delta_12w:.3f} over 12w) [{signal.source}]"
                        ),
                        styles["BodyText"],
                    )
                )
            body.append(Spacer(1, 6))

        body.append(Paragraph("Engagement Breakdown", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Comments/Likes ratio: {profile.engagement_breakdown.comments_to_likes_ratio:.3f}<br/>"
                    f"Repeat commenter density: {profile.engagement_breakdown.repeat_commenter_density:.3f}<br/>"
                    f"UGC depth: {profile.engagement_breakdown.ugc_depth_score:.1f} | "
                    f"Sentiment: {profile.engagement_breakdown.sentiment_score:.1f}"
                ),
                styles["BodyText"],
            )
        )
        body.append(Spacer(1, 10))

        body.append(Paragraph("Financial Inference Model", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Traffic estimate: {profile.financial_inference.traffic_estimate_kmo:.1f}k visits/mo<br/>"
                    f"Conversion assumption: {profile.financial_inference.conversion_assumption_pct:.2f}%<br/>"
                    f"AOV: ${profile.financial_inference.average_order_value_usd:.2f} | "
                    f"SKU estimate: {profile.financial_inference.sku_count_estimate}<br/>"
                    f"Sell-through assumption: {profile.financial_inference.sell_through_assumption_pct:.1f}%<br/>"
                    f"Gross margin estimate: {profile.financial_inference.gross_margin_estimate_pct:.1f}%<br/>"
                    f"CAC proxy: ${profile.financial_inference.cac_proxy_usd:.1f} | "
                    f"LTV proxy: ${profile.financial_inference.ltv_proxy_usd:.1f}"
                ),
                styles["BodyText"],
            )
        )
        for flag in profile.financial_inference.scenario_flags:
            body.append(Paragraph(f"- {flag}", styles["BodyText"]))
        body.append(Spacer(1, 10))

        body.append(Paragraph("Risk + Resilience Scan", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    f"Trademark strength: {profile.risk_scan.trademark_strength}<br/>"
                    f"Corporate registry verified: {'yes' if profile.risk_scan.corporate_registry_verified else 'no'}<br/>"
                    f"Platform dependency: {profile.risk_scan.platform_dependency_risk}<br/>"
                    f"Algorithm exposure: {profile.risk_scan.algorithm_exposure_risk}<br/>"
                    f"Supplier concentration: {profile.risk_scan.supplier_concentration_risk}<br/>"
                    f"Founder dependency score: {profile.risk_scan.founder_dependency_score:.1f}"
                ),
                styles["BodyText"],
            )
        )
        for flag in profile.risk_scan.litigation_flags:
            body.append(Paragraph(f"- {flag}", styles["BodyText"]))
        for item in profile.risk_scan.key_risks[:3]:
            body.append(Paragraph(f"- {item}", styles["BodyText"]))
        body.append(Spacer(1, 10))

        body.append(Paragraph("Structured Outreach Draft", styles["Heading2"]))
        outreach_html = profile.deal_structuring.draft_outreach_email.replace("\n", "<br/>")
        body.append(Paragraph(outreach_html, styles["BodyText"]))
        body.append(Spacer(1, 10))

        body.append(Paragraph("Workflow Alignment", styles["Heading2"]))
        body.append(
            Paragraph(
                (
                    "Workflow: Cultural signal → Engagement analysis → Financial inference → Risk scan → Structured outreach.<br/>"
                    "Principle: prioritize acceleration and rate-of-change over absolute scale."
                ),
                styles["BodyText"],
            )
        )
        body.append(Spacer(1, 12))

        body.append(Paragraph("Key Evidence", styles["Heading2"]))
        for item in profile.evidence[:6]:
            body.append(Paragraph(f"- {item.title} ({item.source})", styles["BodyText"]))

        doc.build(body)

        summary = (
            f"Generated 2-page report for {profile.brand.name} with {profile.scorecard.suggested_deal_structure} "
            f"recommendation, ownership target {profile.deal_structuring.suggested_ownership_target_pct}, and "
            "production/cost-down plan plus data-collection snapshot."
        )

        self._record_generated_report(
            db=db,
            brand_id=profile.brand.id,
            path=str(output_path),
            summary=summary,
        )

        return schemas.ReportArtifact(
            brand_id=profile.brand.id,
            generated_at=timestamp,
            path=str(output_path),
            summary=summary,
        )

    def generate_top_ranked(self, db: Session, limit: int = 20) -> list[schemas.ReportArtifact]:
        feed = build_feed(db=db, sort="heat", limit=limit)
        artifacts: list[schemas.ReportArtifact] = []

        for item in feed.items:
            artifact = self.generate(db=db, req=schemas.ReportRequest(brand_id=item.brand_id))
            artifacts.append(artifact)

        return artifacts
