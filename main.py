"""
main.py — Entry point for the SSA Disability Claims OpenLens MCP Server.

Run with:
    python main.py

Or via the installed console script:
    openlens
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

# Load .env if present (no-op if file doesn't exist)
load_dotenv()

from src.ssa_disability_claims_openlens.app import create_app  # noqa: E402
from src.ssa_disability_claims_openlens.utils import get_logger  # noqa: E402

logger = get_logger("openlens.main")


def main() -> None:
    """Create and run the OpenLens MCP server on stdio transport."""
    logger.info("Starting SSA Disability Claims OpenLens MCP Server...")
    app = create_app()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
        sys.exit(0)
    except Exception as exc:
        logger.exception(f"Fatal error: {exc}")
        sys.exit(1)
