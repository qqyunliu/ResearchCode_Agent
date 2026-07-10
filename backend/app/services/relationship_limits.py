from __future__ import annotations


RELATIONSHIP_LIMITS_HEADING = "Indexed relationship limits:"


def append_relationship_limits(
    answer: str,
    uncertainties: list[str] | tuple[str, ...],
) -> str:
    limits = [
        uncertainty
        for uncertainty in uncertainties
        if uncertainty.startswith("No stored ")
        and "edge was found" in uncertainty
        and "cannot be determined from indexed code" in uncertainty
    ]
    if not limits:
        return answer

    limit_text = "\n".join(f"- {limit}" for limit in limits)
    return f"{answer}\n\n{RELATIONSHIP_LIMITS_HEADING}\n{limit_text}"
