from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import Settings
from ..schemas import BrandProfile, ChatRequest, ChatResponse, EvidenceCitation
from .scoring import build_brand_profile


class ChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _mode_guidance(self, mode: str) -> str:
        if mode == "production_plan":
            return (
                "Mode is production_plan. Build an actionable production-cost plan with sections: "
                "Current production model; Top 3 cheaper production options; 30/60/90-day execution plan; "
                "Expected savings range; key risks and mitigations."
            )
        if mode == "memo":
            return "Mode is memo. Deliver concise investment memo style output with thesis, downside, and structure."
        if mode == "diligence":
            return "Mode is diligence. Emphasize unknowns, verification steps, and confidence caveats."
        return "Mode is analysis. Provide clear synthesis with practical next actions."

    def _fallback_response(self, profile: BrandProfile | None, citations: list[EvidenceCitation], mode: str) -> ChatResponse:
        # Strictly grounded fallback: never invent facts beyond the computed profile context.
        if profile:
            return ChatResponse(
                answer=self._profile_grounded_answer(profile=profile, mode=mode),
                confidence=0.72,
                citations=citations[:6],
                model="fallback-profile-grounded",
            )

        return ChatResponse(
            answer=(
                "AI is not configured (missing OPENROUTER_API_KEY) and no brand context is available. "
                "Select a brand from the feed to get a deterministic, grounded summary, or set OPENROUTER_API_KEY to enable chat."
            ),
            confidence=0.2,
            citations=[],
            model="fallback-no-context",
        )

    @staticmethod
    def _should_force_profile_grounding(answer: str) -> bool:
        lower = answer.lower()
        triggers = [
            "cannot provide",
            "no data",
            "insufficient data",
            "only contains information about",
            "we would need",
            "run a fresh analysis",
            "not enough information",
        ]
        return any(trigger in lower for trigger in triggers)

    def _profile_grounded_answer(self, profile: BrandProfile, mode: str) -> str:
        top_option = profile.production_options[0]
        top_cost = profile.cost_reduction_opportunities[0]
        if mode == "production_plan":
            return (
                f"{profile.brand.name} production cost-down plan:\\n"
                f"Current model: {profile.production_snapshot.current_model}.\\n"
                "Top cheaper options: "
                f"(1) {profile.production_options[0].option_name}, "
                f"(2) {profile.production_options[1].option_name}, "
                f"(3) {profile.production_options[2].option_name}.\\n"
                "30/60/90 plan: "
                "30d baseline unit economics + vendor map, "
                "60d execute targeted rebids/pilots, "
                "90d renegotiate and scale winning production mix.\\n"
                f"Expected savings: {top_cost.estimated_savings_pct_low:.1f}% to "
                f"{top_cost.estimated_savings_pct_high:.1f}% with {top_option.execution_risk} execution risk."
            )
        return (
            f"{profile.brand.name} is currently at Heat {profile.scorecard.heat_score:.1f}, "
            f"Risk {profile.scorecard.risk_score:.1f}, Asymmetry {profile.scorecard.asymmetry_index:.1f}, "
            f"Revenue P50 ${profile.scorecard.revenue_p50:.1f}M. "
            f"Most practical cost-down path is {top_option.option_name} with "
            f"{top_option.estimated_savings_pct:.1f}% estimated savings and "
            f"{top_option.time_to_impact_months} month time-to-impact. "
            f"Deal structure baseline: {profile.deal_structuring.suggested_entry_strategy} "
            f"at {profile.deal_structuring.suggested_ownership_target_pct} ownership target."
        )

    def _extract_json(self, content: str) -> dict[str, Any] | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def chat(self, db: Session, req: ChatRequest) -> ChatResponse:
        profile = build_brand_profile(db, req.brand_id) if req.brand_id else None
        fallback_citations = profile.evidence if profile else []
        profile_name = profile.brand.name if profile else "selected universe"

        if not self.settings.openrouter_api_key:
            return self._fallback_response(profile=profile, citations=fallback_citations, mode=req.mode)

        context_lines = []
        if profile:
            context_lines.extend(
                [
                    f"Brand: {profile.brand.name}",
                    f"Category: {profile.brand.category}",
                    f"Region: {profile.brand.region}",
                    f"Heat: {profile.scorecard.heat_score}",
                    f"Risk: {profile.scorecard.risk_score}",
                    f"Asymmetry: {profile.scorecard.asymmetry_index}",
                    f"Revenue P50: {profile.scorecard.revenue_p50}",
                    f"Capital required: {profile.scorecard.capital_required_musd}",
                    f"Deeper analysis required: {profile.scorecard.deeper_analysis_required}",
                    f"Production model estimate: {profile.production_snapshot.current_model}",
                    f"Unit economics pressure: {profile.production_snapshot.unit_economics_pressure}",
                    "Production bottlenecks:",
                ]
            )
            for bottleneck in profile.production_snapshot.bottlenecks:
                context_lines.append(f"- {bottleneck}")
            context_lines.extend(
                [
                    "Production options:",
                ]
            )
            for option in profile.production_options[:4]:
                context_lines.append(
                    f"- {option.option_name} | mode={option.mode} | savings={option.estimated_savings_pct}% | "
                    f"time={option.time_to_impact_months} months | risk={option.execution_risk}"
                )
            context_lines.extend(
                [
                    "Cost-down opportunities:",
                ]
            )
            for opp in profile.cost_reduction_opportunities[:3]:
                context_lines.append(
                    f"- {opp.title} | lever={opp.lever} | savings={opp.estimated_savings_pct_low}-{opp.estimated_savings_pct_high}%"
                )
            context_lines.append("Data collection layer snapshot (current | delta_12w | source):")
            context_lines.append("Social signals:")
            for signal in profile.data_collection_snapshot.social_signals:
                context_lines.append(
                    f"- {signal.metric} | current={signal.current} | delta_12w={signal.delta_12w} | source={signal.source}"
                )
            context_lines.append("Commerce signals:")
            for signal in profile.data_collection_snapshot.commerce_signals:
                context_lines.append(
                    f"- {signal.metric} | current={signal.current} | delta_12w={signal.delta_12w} | source={signal.source}"
                )
            context_lines.append("Search + cultural signals:")
            for signal in profile.data_collection_snapshot.search_cultural_signals:
                context_lines.append(
                    f"- {signal.metric} | current={signal.current} | delta_12w={signal.delta_12w} | source={signal.source}"
                )
            context_lines.append(f"Acceleration priority note: {profile.data_collection_snapshot.acceleration_priority_note}")
            context_lines.extend(
                [
                    "Engagement breakdown:",
                    (
                        f"- comments_to_likes={profile.engagement_breakdown.comments_to_likes_ratio} | "
                        f"repeat_density={profile.engagement_breakdown.repeat_commenter_density} | "
                        f"sentiment={profile.engagement_breakdown.sentiment_score}"
                    ),
                    "Financial inference:",
                    (
                        f"- traffic_kmo={profile.financial_inference.traffic_estimate_kmo} | "
                        f"conversion_pct={profile.financial_inference.conversion_assumption_pct} | "
                        f"gross_margin_pct={profile.financial_inference.gross_margin_estimate_pct} | "
                        f"cac={profile.financial_inference.cac_proxy_usd} | ltv={profile.financial_inference.ltv_proxy_usd}"
                    ),
                    "Financial scenario flags:",
                ]
            )
            for flag in profile.financial_inference.scenario_flags:
                context_lines.append(f"- {flag}")
            context_lines.extend(
                [
                    "Risk scan summary:",
                    (
                        f"- trademark={profile.risk_scan.trademark_strength} | "
                        f"registry_verified={profile.risk_scan.corporate_registry_verified} | "
                        f"platform_dependency={profile.risk_scan.platform_dependency_risk} | "
                        f"algorithm_exposure={profile.risk_scan.algorithm_exposure_risk} | "
                        f"supplier_concentration={profile.risk_scan.supplier_concentration_risk} | "
                        f"founder_dependency_score={profile.risk_scan.founder_dependency_score}"
                    ),
                    "Deal structuring:",
                    (
                        f"- strategy={profile.deal_structuring.suggested_entry_strategy} | "
                        f"ownership_target={profile.deal_structuring.suggested_ownership_target_pct} | "
                        f"capital_required={profile.deal_structuring.estimated_capital_required_musd}"
                    ),
                    "Founder alignment thesis:",
                    f"- {profile.deal_structuring.founder_alignment_thesis}",
                ]
            )
            context_lines.extend(
                [
                    "Evidence:",
                ]
            )
            for ev in profile.evidence[:10]:
                context_lines.append(f"- {ev.title} | {ev.url} | {ev.source}")

        system_prompt = (
            "You are BURCH-EIDOLON's diligence analyst. Return strict JSON with keys: "
            "answer (string), confidence (0..1), citations (array of objects: title,url,source,snippet). "
            "Always include at least 2 citations if available from provided evidence. "
            "Every answer must stay grounded in the deal-flow workflow and explicitly include production options "
            "plus cost-reduction opportunities when relevant. "
            "Prioritize acceleration/rate-of-change interpretation over absolute scale when signals conflict. "
            "When a brand is selected, include a clear view on ownership target, capital required, and outreach posture."
        )
        mode_guidance = self._mode_guidance(req.mode)
        user_messages = [{"role": m.role, "content": m.content} for m in req.messages]
        workflow_block = (
            "Deal-flow workflow anchor:\\n"
            "Cultural signal → Engagement analysis → Financial inference → Risk scan → Structured outreach\\n\\n"
            "Outputs to include when relevant:\\n"
            "- Heat score (0-100), revenue range proxy, capital intensity proxy, risk score (0-100), asymmetry index\\n"
            "- Suggested deal structure, ownership target, capital required\\n"
            "- Production/cost-down hypotheses and a verification plan\\n\\n"
            "Rule: if evidence is insufficient, say so and list what to verify next. Never invent facts."
        )

        payload = {
            "model": self.settings.openrouter_strong_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": mode_guidance},
                {"role": "system", "content": workflow_block},
                {"role": "system", "content": "\n".join(context_lines)[: self.settings.openrouter_max_input_tokens]},
                *user_messages,
            ],
            "max_tokens": self.settings.openrouter_max_output_tokens,
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.burch-eidolon",
            "X-Title": "BURCH-EIDOLON",
        }

        try:
            with httpx.Client(timeout=25.0) as client:
                response = client.post(
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return self._fallback_response(profile=profile, citations=fallback_citations, mode=req.mode)

        raw_content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        parsed = self._extract_json(raw_content)
        if not parsed:
            return self._fallback_response(profile=profile, citations=fallback_citations, mode=req.mode)

        citations_payload = parsed.get("citations") or []
        citations: list[EvidenceCitation] = []
        for c in citations_payload[:8]:
            if not isinstance(c, dict):
                continue
            title = str(c.get("title", "Untitled citation"))
            url = str(c.get("url", ""))
            source = str(c.get("source", "unknown"))
            snippet = str(c.get("snippet", ""))
            citations.append(EvidenceCitation(title=title, url=url, source=source, snippet=snippet))

        if not citations:
            citations = fallback_citations[:4]

        try:
            confidence = float(parsed.get("confidence", 0.55))
        except Exception:
            confidence = 0.55
        confidence = max(0.0, min(1.0, confidence))

        answer = str(parsed.get("answer", "Insufficient model output; returning conservative summary."))

        # Guardrail: if a brand is selected, reject model responses that deny available context.
        if profile and self._should_force_profile_grounding(answer):
            return ChatResponse(
                answer=self._profile_grounded_answer(profile=profile, mode=req.mode),
                confidence=max(0.72, confidence),
                citations=citations[:6],
                model=f"{data.get('model', self.settings.openrouter_strong_model)}+guardrail",
            )

        if profile and profile.brand.name.lower() not in answer.lower():
            answer = f"{profile.brand.name}: {answer}"

        return ChatResponse(
            answer=answer,
            confidence=confidence,
            citations=citations,
            model=data.get("model", self.settings.openrouter_strong_model),
        )
