"""
Resource: transparency_recommendations

Exposes the full transparency recommendation catalog as a readable MCP resource.
Provides a structured view of all known SSA data gaps and improvement opportunities.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from ..services.recommendation_service import RecommendationService
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://recommendations/transparency",
        name="transparency_recommendations",
        description=(
            "Full catalog of known SSA public data transparency gaps and prioritized "
            "improvement recommendations. Organized by topic area: processing times, "
            "demographic equity, field office access, geographic equity, work incentives, "
            "and SSI adequacy. Use as a reference for data publication planning."
        ),
        mime_type="application/json",
    )
    def transparency_recommendations() -> str:
        """Return all transparency recommendations across all topics."""
        try:
            svc = RecommendationService()
            # Generate recommendations across all known topic areas
            topics = [
                "processing time wait backlog delay",
                "race ethnicity demographic equity disparit",
                "field office access appointment location",
                "geographic state county region rural",
                "work employment ticket return incentive",
                "ssi supplemental adequacy poverty income",
            ]
            all_recs: list[dict[str, Any]] = []
            seen_titles: set[str] = set()
            for topic in topics:
                plan = svc.generate_recommendations(context=topic, max_recommendations=5)
                for rec in plan.recommendations:
                    if rec.title not in seen_titles:
                        seen_titles.add(rec.title)
                        all_recs.append(rec.model_dump(mode="json"))

            return json.dumps(
                {
                    "total_recommendations": len(all_recs),
                    "recommendations": all_recs,
                },
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"transparency_recommendations resource failed: {exc}")
            return json.dumps({"error": str(exc)})
