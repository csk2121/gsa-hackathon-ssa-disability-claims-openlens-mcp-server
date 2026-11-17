"""MCP prompts package — exports all prompt modules for registration."""

from . import (
    answer_coverage_evaluator,
    openlens_dataset_advisor,
    transparency_reviewer,
)

__all__ = [
    "answer_coverage_evaluator",
    "openlens_dataset_advisor",
    "transparency_reviewer",
]
