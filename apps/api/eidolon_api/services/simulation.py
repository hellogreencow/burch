from __future__ import annotations

import numpy as np

from ..schemas import PercentileBand, ScenarioResult, SimulateRequest

SCENARIO_PARAMS = {
    "meta_cpm_spike": {"rev_mu": -0.08, "rev_sigma": 0.06, "margin_mu": -0.05, "margin_sigma": 0.03, "risk": 7.5},
    "tiktok_ban": {"rev_mu": -0.14, "rev_sigma": 0.08, "margin_mu": -0.06, "margin_sigma": 0.04, "risk": 12.0},
    "wholesale_contraction": {
        "rev_mu": -0.11,
        "rev_sigma": 0.07,
        "margin_mu": -0.03,
        "margin_sigma": 0.03,
        "risk": 9.0,
    },
}


def _band(values: np.ndarray) -> PercentileBand:
    return PercentileBand(
        p10=float(np.percentile(values, 10)),
        p50=float(np.percentile(values, 50)),
        p90=float(np.percentile(values, 90)),
    )


def run_simulation(req: SimulateRequest) -> ScenarioResult:
    params = SCENARIO_PARAMS[req.preset]
    seed = req.seed + (sum(ord(ch) for ch in req.brand_id) % 10000)
    rng = np.random.default_rng(seed)

    revenue_deltas = rng.normal(loc=params["rev_mu"], scale=params["rev_sigma"], size=req.iterations)
    margin_deltas = rng.normal(loc=params["margin_mu"], scale=params["margin_sigma"], size=req.iterations)

    # constrain extreme outliers for stability
    revenue_deltas = np.clip(revenue_deltas, -0.5, 0.3)
    margin_deltas = np.clip(margin_deltas, -0.35, 0.2)

    result = ScenarioResult(
        brand_id=req.brand_id,
        preset=req.preset,
        seed=req.seed,
        outcomes={
            "revenue_delta_pct": _band(revenue_deltas * 100),
            "margin_delta_pct": _band(margin_deltas * 100),
            "risk_shift": round(float(params["risk"]), 3),
        },
    )
    return result
