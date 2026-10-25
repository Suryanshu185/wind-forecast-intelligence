"""Command line: ``python -m app.cli ingest | verify-snapshot | describe``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.config import get_settings
from app.ingestion.elexon_client import ElexonClient, ElexonError
from app.ingestion.snapshot import SnapshotError, load_snapshot, write_snapshot

TOOL_VERSION = "0.1.0"
PUBLISH_LOOKBACK_DAYS = 5  # covers cutoffs up to D-3 with margin (see architecture doc)
PUBLISH_LOOKAHEAD_DAYS = 4  # post-delivery vintages shown (as context) in the revision explorer


def ingest(start: date, end: date, out: Path, base_url: str, timeout: float, retries: int) -> int:
    publish_from = datetime(start.year, start.month, start.day, tzinfo=UTC) - timedelta(
        days=PUBLISH_LOOKBACK_DAYS
    )
    publish_to = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(
        days=PUBLISH_LOOKAHEAD_DAYS
    )
    try:
        # Fetch everything BEFORE touching the output directory: a failure leaves it unchanged.
        with ElexonClient(base_url, timeout=timeout, max_retries=retries) as client:
            fuelhh = client.fetch_fuelhh_wind(start, end)
            windfor = client.fetch_windfor(publish_from, publish_to)
        manifest = write_snapshot(
            out,
            fuelhh,
            windfor,
            delivery_start=start,
            delivery_end=end,
            publish_from=publish_from,
            publish_to=publish_to,
            tool_version=TOOL_VERSION,
        )
    except ElexonError as exc:
        print(f"INGEST FAILED (existing snapshot untouched): {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "written_to": str(out),
                "data_sha256": manifest["data_sha256"],
                "retrieved_at": manifest["retrieved_at"],
                "rows": {k: v["rows"] for k, v in manifest["files"].items()},
            },
            indent=2,
        )
    )
    return 0


def verify(directory: Path) -> int:
    try:
        snap = load_snapshot(directory)
    except SnapshotError as exc:
        print(f"SNAPSHOT INVALID: {exc}", file=sys.stderr)
        return 2
    m = snap.manifest
    print(
        f"OK  synthetic={m['is_synthetic']}  retrieved_at={m['retrieved_at']}  sha256={m['data_sha256'][:16]}..."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser(
        "ingest", help="Fetch real data from Elexon and write a verified snapshot"
    )
    p_ing.add_argument("--start", type=date.fromisoformat, default=s.analysis_start_date)
    p_ing.add_argument("--end", type=date.fromisoformat, default=s.analysis_end_date)
    p_ing.add_argument("--out", type=Path, default=s.data_snapshot_dir)
    p_ver = sub.add_parser("verify-snapshot", help="Check snapshot hashes and row counts")
    p_ver.add_argument("--dir", type=Path, default=s.data_snapshot_dir)
    args = parser.parse_args(argv)
    if args.cmd == "ingest":
        return ingest(
            args.start,
            args.end,
            args.out,
            s.elexon_base_url,
            s.elexon_timeout_seconds,
            s.elexon_max_retries,
        )
    return verify(args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
