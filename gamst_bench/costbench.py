"""CostBench aggregation helpers.

These helpers only aggregate quantities already present in scored rows. They
never estimate missing provider, device, or idle-capacity costs; an unknown
component keeps the aggregate unknown.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            result = Decimal(str(value))
        except Exception:
            return None
        if result.is_finite() and result >= 0:
            return result
    return None


def aggregate_costs(rows: list[dict[str, Any]], rate_card: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Aggregate scored rows into a CostBench-compatible, audit-aware summary.

    ``cost_usd_exact`` is preferred because it preserves decimal arithmetic.
    Missing cost or incomplete accounting makes the total explicitly unknown.
    """
    quantities: dict[str, Decimal] = {}
    complete = True
    for row in rows:
        exact = _decimal(row.get("cost_usd_exact"))
        if exact is None or row.get("cost_usd") is None:
            complete = False
        cost_components = row.get("cost_components")
        if isinstance(cost_components, dict) and cost_components:
            for key, value in cost_components.items():
                amount = _decimal(value)
                if amount is None:
                    complete = False
                else:
                    quantities[key] = quantities.get(key, Decimal(0)) + amount
        elif exact is not None:
            # Some scored rows expose only a provider-agnostic exact total.
            # Retain that measured amount under an explicit unattributed
            # component instead of claiming the aggregate is unknown.
            quantities["unattributed"] = quantities.get("unattributed", Decimal(0)) + exact
    with localcontext() as ctx:
        ctx.prec = 80
        total = sum(quantities.values(), Decimal(0)) if complete and quantities else None
    return {
        "schema_version": 1,
        "kind": "costbench_aggregate",
        "status": "measured" if complete else "unknown",
        "rows": len(rows),
        "components_usd_exact": {k: str(v) for k, v in sorted(quantities.items())},
        "total_usd_exact": str(total) if total is not None else None,
        "rate_card_revision": sorted({str(v.get("revision")) for v in rate_card.values()}) if rate_card else [],
        "scope": "scored rows only; provider/device/idle costs remain unknown unless instrumented",
    }


def select_default(*, evidence: str, comparisons: list[dict[str, Any]], candidate: str) -> dict[str, Any]:
    """Return a conservative default-selection decision.

    Synthetic and numerically passing-but-unaudited runs can never promote a
    default. Every comparison must pass its independent-audit gate.
    """
    if evidence != "measured":
        return {"selected": None, "status": "unmeasured", "reason": "synthetic evidence cannot promote a default"}
    if not comparisons or any(c.get("status") != "numeric_pass_requires_audit" for c in comparisons):
        return {"selected": None, "status": "not_passed", "reason": "all preregistered comparisons must pass"}
    if any(c.get("audit_status") != "approved" for c in comparisons):
        return {"selected": None, "status": "independent_audit_required", "reason": "numeric pass requires independent audit"}
    return {"selected": candidate, "status": "approved", "reason": "all comparisons passed and were independently audited"}
