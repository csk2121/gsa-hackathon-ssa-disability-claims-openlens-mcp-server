"""
Shared tool plumbing: parameter types, tool annotations and error handling.

Parameter types
---------------
Each tool parameter is declared with ``Annotated[..., Field(...)]`` so its
description and limits appear in the tool's published input schema. The model
sees the rules before it calls the tool, and FastMCP rejects out-of-range input
before any tool code runs. The limits also cap how much caller-supplied text the
server will process or echo back.

Errors
------
Tools raise ``ToolError`` instead of returning ``{"error": ...}``, so failures
reach the client with ``isError: true``. Unexpected exceptions are logged in full
on the server and replaced with a generic message, so internal details (paths,
URLs, stack traces) are never sent to the client.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from ..utils import get_logger

logger = get_logger(__name__)

# ── Parameter types ────────────────────────────────────────────────────────────

# Catalog IDs ("ssa-hearing-office-workload") and live IDs ("datagov-<slug>") are
# lowercase slugs. The pattern rejects path separators, dots, spaces and
# control characters outright.
DatasetId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description=(
            "Dataset ID from discover_disability_datasets, "
            "e.g. 'ssa-hearing-office-workload'."
        ),
    ),
]

Question = Annotated[
    str,
    Field(
        min_length=10,
        max_length=500,
        description=(
            "A natural-language question to test against SSA public data, e.g. "
            "'How long are people waiting for disability decisions by state?'"
        ),
    ),
]

RecommendationContext = Annotated[
    str,
    Field(
        min_length=10,
        max_length=20_000,
        description=(
            "A question, topic or identified gap. Passing the full report from "
            "evaluate_answer_coverage gives the most targeted recommendations."
        ),
    ),
]

FocusArea = Annotated[
    str | None,
    Field(
        default=None,
        max_length=200,
        description="Optional area to narrow recommendations, e.g. 'processing times'.",
    ),
]

MaxRecommendations = Annotated[
    int,
    Field(ge=1, le=20, description="Maximum number of recommendations to return (1–20)."),
]

SearchQuery = Annotated[
    str | None,
    Field(
        default=None,
        max_length=200,
        description="Optional keyword search, e.g. 'SSDI', 'field office', 'appeals'.",
    ),
]

SourceFilter = Annotated[
    Literal["SSA Open Data Portal", "Data.gov", "Static Catalog"] | None,
    Field(default=None, description="Optional: only return datasets from this source."),
]

Tag = Annotated[str, Field(min_length=1, max_length=60)]

Tags = Annotated[
    list[Tag] | None,
    Field(
        default=None,
        max_length=20,
        description="Optional subject tags to filter by, e.g. ['appeals', 'geographic'].",
    ),
]

DatasetIds = Annotated[
    list[DatasetId],
    Field(
        min_length=2,
        max_length=10,
        description="Two to ten distinct dataset IDs from discover_disability_datasets.",
    ),
]

FocusDimensions = Annotated[
    list[Literal["geographic", "temporal", "operational"]] | None,
    Field(
        default=None,
        max_length=3,
        description="Optional: score only these dimensions instead of all three.",
    ),
]

# ── Tool annotations ───────────────────────────────────────────────────────────
# Every tool only reads catalog metadata: nothing is created, changed or deleted,
# and repeating a call returns the same result. Hosts use these hints to decide
# whether a call needs the user's confirmation.

READ_ONLY_CLOSED = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# discover_disability_datasets also searches the live Data.gov catalog.
READ_ONLY_OPEN = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

# ── Errors ─────────────────────────────────────────────────────────────────────


def dataset_not_found(dataset_id: str) -> ToolError:
    """Error for an ID that passed validation but is not in the catalog."""
    return ToolError(
        f"Dataset '{dataset_id}' not found. "
        "Use discover_disability_datasets to get valid dataset IDs."
    )


@contextmanager
def tool_errors(tool_name: str) -> Iterator[None]:
    """
    Turn exceptions raised inside a tool into client-safe ToolErrors.

    ToolError passes through unchanged. Validation errors keep pydantic's
    message (never the rejected input). Anything else is logged with its
    traceback and reported to the client as a generic internal error.
    """
    try:
        yield
    except ToolError:
        raise
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first.get("loc", ())) or "input"
        raise ToolError(f"Invalid {field}: {first.get('msg', 'invalid value')}") from None
    except Exception:
        logger.exception(f"{tool_name} failed")
        raise ToolError(
            f"{tool_name} failed because of an internal error. "
            "Try again; if it keeps failing, report it to the server maintainer."
        ) from None
