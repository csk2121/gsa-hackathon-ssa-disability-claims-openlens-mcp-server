#!/usr/bin/env python3
"""
Re-check every "no public data" claim the server makes against SSA's Data.gov catalog.

Reads src/ssa_disability_claims_openlens/data/gap_evidence.json. For each claim it
runs the recorded searches (SSA datasets with downloads only) and compares the hits
with the hits a person has already reviewed. A new, unreviewed hit may mean SSA has
published data that contradicts the claim, so the script exits 1 and prints it.

Usage:
    python scripts/check_gap_claims.py           # report; exit 1 on unreviewed hits
    python scripts/check_gap_claims.py --stamp   # also set searched_on to today when clean

To resolve an unreviewed hit, open its Data.gov page, then either add it to the
claim's reviewed_hits with a one-line note on why it does not close the gap, or
change the coverage rating in answer_coverage_service.py and remove the claim.

Standard library only. Exit codes: 0 clean, 1 unreviewed hits, 2 API unreachable.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

SEARCH_URL = "https://catalog.data.gov/api/v1/search"
USER_AGENT = "ssa-openlens-gap-check/1.0"
EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "ssa_disability_claims_openlens" / "data" / "gap_evidence.json"
)


def search(query: str, params: dict[str, Any]) -> dict[str, str]:
    """Return {identifier: title} for one search."""
    url = SEARCH_URL + "?" + urllib.parse.urlencode({"q": query, **params})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        results = json.load(resp).get("results", [])
    hits: dict[str, str] = {}
    for r in results:
        dcat = r.get("dcat") or {}
        ident = dcat.get("identifier") or r.get("slug")
        if ident:
            hits[str(ident)] = str(dcat.get("title", ""))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stamp", action="store_true", help="set searched_on to today when no unreviewed hits")
    args = parser.parse_args()

    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    params = evidence["search_params"]
    unreviewed_total = 0

    for claim, entry in evidence["claims"].items():
        hits: dict[str, str] = {}
        try:
            for q in entry["queries"]:
                hits.update(search(q, params))
        except urllib.error.URLError as exc:
            print(f"ERROR: Data.gov unreachable ({exc})", file=sys.stderr)
            return 2
        reviewed = entry.get("reviewed_hits", {})
        new = {k: v for k, v in hits.items() if k not in reviewed}
        status = "ok" if not new else f"{len(new)} UNREVIEWED"
        print(f"[{status:>13}] {claim}  ({len(hits)} hits, {len(reviewed)} reviewed)")
        for ident, title in sorted(new.items()):
            print(f"                  {ident}  {title}")
        unreviewed_total += len(new)

    if unreviewed_total:
        print(f"\n{unreviewed_total} unreviewed hit(s). Review each one before trusting the gap claims.")
        return 1

    if args.stamp:
        evidence["searched_on"] = date.today().isoformat()
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nAll hits reviewed; searched_on set to {evidence['searched_on']}.")
    else:
        print("\nAll hits reviewed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
