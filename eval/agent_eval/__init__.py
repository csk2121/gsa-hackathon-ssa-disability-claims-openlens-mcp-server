"""
Agent-level evaluation for SSA Disability Claims OpenLens.

A Claude agent answers a fixed test set (openlens-eval-0) by calling the real
MCP server over stdio, the way Claude Code does. Each answer is scored by code
checks (tool choice, rating, report fidelity, invented numbers, expectations)
and by two LLM judges (correctness, grounding). Every run is saved as an
experiment, and report.py charts the experiments side by side.

    python -m eval.agent_eval.run --check-setup     # no API calls
    python -m eval.agent_eval.run --prompt v01      # run an experiment
    python -m eval.agent_eval.report                # rebuild the report
"""
