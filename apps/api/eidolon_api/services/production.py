from __future__ import annotations

from dataclasses import dataclass

from .. import schemas


@dataclass
class ProductionInputs:
    category: str
    heat_score: float
    risk_score: float
    asymmetry_index: float
    capital_intensity: float
    revenue_p50: float
    confidence: float


CATEGORY_HINTS = {
    "Beauty": "formula and packaging suppliers",
    "Personal Care": "contract fill-finish and packaging suppliers",
    "Food & Beverage": "co-packers and ingredient procurement",
    "Apparel": "cut-and-sew partners and fabric sourcing",
    "Home Goods": "tooling vendors and freight lanes",
    "Consumer Tech": "OEM assembly and component sourcing",
    "Pet": "co-manufacturing and packaging",
    "Outdoor": "materials sourcing and fulfillment footprint",
    "Childcare": "compliance-grade suppliers and packaging",
    "Wellness": "ingredient sourcing and contract manufacturing",
}


def _current_model(inputs: ProductionInputs) -> str:
    if inputs.capital_intensity < 38:
        return "Asset-light contract manufacturing"
    if inputs.capital_intensity < 68:
        return "Hybrid model (contract manufacturing plus controlled finishing/assembly)"
    return "Capex-heavy dedicated line or in-house production"


def _pressure_label(inputs: ProductionInputs) -> str:
    pressure = (inputs.capital_intensity * 0.55 + inputs.risk_score * 0.45) / 100
    if pressure < 0.42:
        return "low-to-moderate"
    if pressure < 0.68:
        return "moderate-to-high"
    return "high"


def _bottlenecks(inputs: ProductionInputs) -> list[str]:
    bottlenecks: list[str] = []
    if inputs.capital_intensity > 58:
        bottlenecks.append("working-capital drag from inventory and MOQs")
    if inputs.risk_score > 62:
        bottlenecks.append("supplier concentration and channel fragility")
    if inputs.heat_score > 72 and inputs.revenue_p50 < 22:
        bottlenecks.append("demand outpacing production planning cadence")
    if inputs.asymmetry_index > 70:
        bottlenecks.append("margin leakage from fragmented vendor terms")

    if not bottlenecks:
        bottlenecks.append("limited procurement leverage at current scale")
    return bottlenecks


def build_production_snapshot(inputs: ProductionInputs) -> schemas.ProductionSnapshot:
    return schemas.ProductionSnapshot(
        current_model=_current_model(inputs),
        unit_economics_pressure=_pressure_label(inputs),
        bottlenecks=_bottlenecks(inputs),
        confidence=round(max(0.35, min(0.95, inputs.confidence - 0.05)), 3),
    )


def _base_savings(inputs: ProductionInputs) -> float:
    # Higher capital intensity and risk create more recoverable inefficiency.
    return max(2.0, min(14.0, 2.0 + (inputs.capital_intensity * 0.08) + (inputs.risk_score * 0.05)))


def build_production_options(inputs: ProductionInputs) -> list[schemas.ProductionOption]:
    base = _base_savings(inputs)
    supplier_hint = CATEGORY_HINTS.get(inputs.category, "supplier network")

    options = [
        schemas.ProductionOption(
            option_name="Strategic Contract Rebid",
            mode="outsource",
            estimated_savings_pct=round(base * 0.7, 2),
            capex_impact_musd=0.4,
            time_to_impact_months=3,
            execution_risk="low",
            rationale=(
                f"Run structured RFP across {supplier_hint} to compress COGS and lock better terms with dual-source coverage."
            ),
        ),
        schemas.ProductionOption(
            option_name="Hybrid Regionalization",
            mode="hybrid",
            estimated_savings_pct=round(base * 0.95, 2),
            capex_impact_musd=1.4,
            time_to_impact_months=6,
            execution_risk="medium",
            rationale="Split production by region to reduce freight, improve lead times, and protect against single-node disruption.",
        ),
        schemas.ProductionOption(
            option_name="SKU + Packaging Simplification",
            mode="licensing",
            estimated_savings_pct=round(base * 0.8, 2),
            capex_impact_musd=0.2,
            time_to_impact_months=4,
            execution_risk="low",
            rationale="Rationalize long-tail SKUs and standardize components to lower MOQ waste and conversion complexity.",
        ),
        schemas.ProductionOption(
            option_name="Selective In-House Critical Process",
            mode="inhouse",
            estimated_savings_pct=round(base * 1.1, 2),
            capex_impact_musd=4.8,
            time_to_impact_months=12,
            execution_risk="high",
            rationale="Internalize the single highest-margin-loss step only when scale and utilization can support fixed-cost absorption.",
        ),
    ]
    return options


def build_cost_reduction_opportunities(inputs: ProductionInputs) -> list[schemas.CostOpportunity]:
    base = _base_savings(inputs)
    confidence = max(0.35, min(0.93, inputs.confidence - 0.08))

    return [
        schemas.CostOpportunity(
            title="Supplier portfolio rebalance",
            lever="procurement",
            estimated_savings_pct_low=round(base * 0.45, 2),
            estimated_savings_pct_high=round(base * 0.9, 2),
            confidence=round(confidence, 3),
            rationale="Reprice top spend categories with volume commitments and indexed terms.",
        ),
        schemas.CostOpportunity(
            title="Freight + fulfillment lane optimization",
            lever="logistics",
            estimated_savings_pct_low=round(base * 0.25, 2),
            estimated_savings_pct_high=round(base * 0.55, 2),
            confidence=round(max(0.3, confidence - 0.05), 3),
            rationale="Use regional 3PL split and demand-cluster routing to reduce landed cost volatility.",
        ),
        schemas.CostOpportunity(
            title="SKU and packaging architecture cleanup",
            lever="product mix",
            estimated_savings_pct_low=round(base * 0.3, 2),
            estimated_savings_pct_high=round(base * 0.6, 2),
            confidence=round(max(0.32, confidence - 0.02), 3),
            rationale="Reduce low-velocity SKU drag and standardize packaging components.",
        ),
    ]
