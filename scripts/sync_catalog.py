#!/usr/bin/env python3
"""
Sync the OpenLens dataset catalog with SSA's official Data.gov metadata records.

Reads  src/ssa_disability_claims_openlens/data/catalog_sources.json
Writes src/ssa_disability_claims_openlens/data/datagov_snapshot.json

For every catalog entry mapped to a Data.gov slug, this fetches the DCAT record from
the Data.gov catalog API (https://catalog.data.gov/api/v1/dataset/{slug}) and stores
the facts the server is allowed to show: title, description, landing page, download
URLs, data dictionary, last-modified date, update frequency and temporal coverage.

The server never invents these facts; it only renders what is in the snapshot.

Usage:
    python scripts/sync_catalog.py            # refresh the snapshot
    python scripts/sync_catalog.py --check    # exit 1 if the snapshot is out of date

Standard library only, so it can run in CI without installing the package.
Exit codes: 0 ok, 1 snapshot differs from Data.gov (--check), 2 a source record is
missing, is not published by SSA, or the API is unreachable.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API_BASE = "https://catalog.data.gov/api/v1/dataset/"
DATASET_PAGE_BASE = "https://catalog.data.gov/dataset/"
EXPECTED_PUBLISHER = "Social Security Administration"
USER_AGENT = "ssa-openlens-catalog-sync/1.0"

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "ssa_disability_claims_openlens" / "data"
SOURCES_PATH = DATA_DIR / "catalog_sources.json"
SNAPSHOT_PATH = DATA_DIR / "datagov_snapshot.json"


class SyncError(Exception):
    """A source record could not be fetched or failed validation."""


def _fetch_dcat(slug: str) -> dict[str, Any]:
    url = API_BASE + urllib.parse.quote(slug, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SyncError(f"{slug}: Data.gov returned HTTP {exc.code} (dataset retired or slug wrong?)") from exc
    except urllib.error.URLError as exc:
        raise SyncError(f"{slug}: Data.gov unreachable ({exc.reason})") from exc

    results = payload.get("results") or []
    if not results:
        raise SyncError(f"{slug}: no record returned")
    record = results[0]
    if record.get("slug") != slug:
        raise SyncError(f"{slug}: API returned a different dataset ({record.get('slug')!r})")
    dcat = record.get("dcat") or {}
    publisher = (dcat.get("publisher") or {}).get("name")
    if publisher != EXPECTED_PUBLISHER:
        raise SyncError(f"{slug}: publisher is {publisher!r}, expected {EXPECTED_PUBLISHER!r}")
    return dcat


def _access_url(value: Any) -> str | None:
    """DCAT fields like landingPage/describedBy are either a URL string or {accessURL: ...}."""
    if isinstance(value, dict):
        value = value.get("accessURL") or value.get("downloadURL")
    return value if isinstance(value, str) and value.startswith("https://") else None


def _temporal(dcat: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = dcat.get("temporal")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, None
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        start, end = raw[0].get("startDate"), raw[0].get("endDate")
        return (start[:10] if start else None), (end[:10] if end else None)
    return None, None


def _normalise(dataset_id: str, slug: str, dcat: dict[str, Any]) -> dict[str, Any]:
    distributions = []
    for dist in dcat.get("distribution") or []:
        url = _access_url(dist.get("downloadURL")) or _access_url(dist.get("accessURL"))
        if url:
            distributions.append({"format": dist.get("format") or "", "url": url})
    start, end = _temporal(dcat)
    return {
        "dataset_id": dataset_id,
        "slug": slug,
        "identifier": dcat.get("identifier"),
        "title": (dcat.get("title") or "").strip(),
        "description": (dcat.get("description") or "").strip(),
        "publisher": EXPECTED_PUBLISHER,
        "modified": (dcat.get("modified") or "")[:10] or None,
        "accrual_periodicity": dcat.get("accrualPeriodicity"),
        "temporal_start": start,
        "temporal_end": end,
        "landing_page": _access_url(dcat.get("landingPage")),
        "data_dictionary": _access_url(dcat.get("describedBy")),
        "distributions": distributions,
        "datagov_url": DATASET_PAGE_BASE + slug,
    }


def build_snapshot(sources: dict[str, Any]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    errors: list[str] = []
    for dataset_id, slug in sorted(sources["datagov"].items()):
        try:
            records[dataset_id] = _normalise(dataset_id, slug, _fetch_dcat(slug))
            print(f"  ok    {dataset_id:38s} <- {slug}")
        except SyncError as exc:
            errors.append(str(exc))
            print(f"  FAIL  {dataset_id:38s} <- {exc}", file=sys.stderr)
    if errors:
        raise SyncError(f"{len(errors)} source record(s) failed:\n  " + "\n  ".join(errors))
    return {
        "_comment": "Generated by scripts/sync_catalog.py from Data.gov DCAT records. Do not edit by hand.",
        "api_base": API_BASE,
        "synced_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed snapshot is out of date")
    args = parser.parse_args()

    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    print(f"Fetching {len(sources['datagov'])} Data.gov records ...")
    try:
        snapshot = build_snapshot(sources)
    except SyncError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        current = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")) if SNAPSHOT_PATH.exists() else {}
        if current.get("records") != snapshot["records"]:
            print("\nSnapshot is out of date. Run: python scripts/sync_catalog.py", file=sys.stderr)
            return 1
        print("\nSnapshot is up to date.")
        return 0

    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {SNAPSHOT_PATH.relative_to(Path.cwd()) if SNAPSHOT_PATH.is_relative_to(Path.cwd()) else SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
