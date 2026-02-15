from __future__ import annotations

from dataclasses import dataclass


GROUNDING_DOC_TITLE = "Deal Flow Engine - Brand Intelligence & Deal Sourcing Engine"

# Distilled requirements from the source document.
GROUNDING_PRINCIPLES = [
    "Prioritize acceleration and rate-of-change over absolute scale.",
    "Use the workflow: Cultural signal -> Engagement analysis -> Financial inference -> Risk scan -> Structured outreach.",
    "Rank a weekly universe and generate deeper analysis for top opportunities.",
    "Combine cultural heat and financial asymmetry with explicit risk scanning.",
    "Generate structured recommendations and outreach-ready theses.",
]

GROUNDING_OUTPUT_EXPECTATIONS = [
    "Output confidence-scored heat, revenue range, capital intensity, risk profile, and asymmetry.",
    "Include stress scenarios such as CPM spikes and platform shocks.",
    "Surface suggested deal structures with clear reasoning.",
]


@dataclass
class GroundingContext:
    title: str
    principles: list[str]
    output_expectations: list[str]


def get_grounding_context() -> GroundingContext:
    return GroundingContext(
        title=GROUNDING_DOC_TITLE,
        principles=list(GROUNDING_PRINCIPLES),
        output_expectations=list(GROUNDING_OUTPUT_EXPECTATIONS),
    )


def format_grounding_block() -> str:
    lines = [
        "Workflow anchor:",
        ]
    lines.extend([f"- {line}" for line in GROUNDING_PRINCIPLES])
    lines.append("Outputs:")
    lines.extend([f"- {line}" for line in GROUNDING_OUTPUT_EXPECTATIONS])
    return "\n".join(lines)
