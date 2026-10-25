"""Snapshot persistence with provenance (manifest.json) and integrity verification.

A snapshot stores the *verbatim* API rows (sorted for reproducibility) so that normalisation - including
duplicate / conflict detection - always runs at load time and conflicts stay observable.
Files: fuelhh_wind.csv.gz, windfor.csv.gz, manifest.json.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.ingestion.elexon_client import FetchResult

SCHEMA_VERSION = 1
FUELHH_FILE = "fuelhh_wind.csv.gz"
WINDFOR_FILE = "windfor.csv.gz"
MANIFEST_FILE = "manifest.json"
FUELHH_COLUMNS = (
    "dataset",
    "publishTime",
    "startTime",
    "settlementDate",
    "settlementPeriod",
    "fuelType",
    "generation",
)
WINDFOR_COLUMNS = ("dataset", "publishTime", "startTime", "generation")

ATTRIBUTION = "Contains BMRS data (c) Elexon Limited copyright and database right."
LIMITATIONS = (
    "FUELHH WIND and WINDFOR may not cover the same set of generators; differences between them may "
    "reflect dataset scope as well as forecast performance (docs/planning/04-data-research-notes.md s10).",
    "WINDFOR is hourly while FUELHH is half-hourly; the hourly forecast is shared by two half-hours.",
    "Whether a WINDFOR row stamped T describes the hour starting or ending at T is not documented; "
    "'start' is an unverified assumption.",
    "The Insights API serves one FUELHH value per interval; later corrections (if any) are not observable.",
    "publishTime is the BMRS publication timestamp; real-world availability to a trader may lag it.",
    "Snapshot is a point-in-time copy; Elexon may revise or withdraw upstream data.",
)


class SnapshotError(Exception):
    pass


class SnapshotNotFoundError(SnapshotError):
    pass


class SnapshotIntegrityError(SnapshotError):
    pass


@dataclass(slots=True)
class RawSnapshot:
    fuelhh_rows: list[dict[str, Any]]
    windfor_rows: list[dict[str, Any]]
    manifest: dict[str, Any]


def _z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _gz_csv_bytes(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    ordered = sorted(rows, key=lambda r: (str(r.get("startTime")), str(r.get("publishTime"))))
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in ordered:
        writer.writerow([_cell(row.get(c)) for c in columns])
    out = io.BytesIO()
    # mtime=0 and empty filename -> byte-for-byte reproducible output for identical input.
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    return out.getvalue()


def _parse_number(text: str) -> int | float | None:
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return float(text)


def _read_gz_csv(data: bytes, columns: Sequence[str]) -> list[dict[str, Any]]:
    try:
        text = gzip.decompress(data).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise SnapshotIntegrityError(f"cannot decompress snapshot file: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != tuple(columns):
        raise SnapshotIntegrityError(f"unexpected CSV header {reader.fieldnames!r}")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        row: dict[str, Any] = dict(rec)
        row["generation"] = _parse_number(rec["generation"])
        if "settlementPeriod" in row:
            row["settlementPeriod"] = int(rec["settlementPeriod"])
        rows.append(row)
    return rows


def encode_files(
    fuelhh_rows: Sequence[Mapping[str, Any]], windfor_rows: Sequence[Mapping[str, Any]]
) -> tuple[bytes, bytes]:
    return (
        _gz_csv_bytes(fuelhh_rows, FUELHH_COLUMNS),
        _gz_csv_bytes(windfor_rows, WINDFOR_COLUMNS),
    )


def build_manifest(
    *,
    fuelhh_bytes: bytes,
    windfor_bytes: bytes,
    fuelhh_row_count: int,
    windfor_row_count: int,
    sources: list[dict[str, Any]],
    retrieved_at: datetime,
    delivery_start: date,
    delivery_end: date,
    publish_from: datetime,
    publish_to: datetime,
    is_synthetic: bool,
    tool_version: str,
    notice: str | None = None,
) -> dict[str, Any]:
    fh_hash, wf_hash = _sha256(fuelhh_bytes), _sha256(windfor_bytes)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "is_synthetic": is_synthetic,
        "description": "Verbatim Elexon Insights API rows (FUELHH WIND actuals, WINDFOR forecast vintages).",
        "retrieved_at": _z(retrieved_at),
        "period_covered": {
            "delivery_start": delivery_start.isoformat(),
            "delivery_end": delivery_end.isoformat(),
            "windfor_publish_from": _z(publish_from),
            "windfor_publish_to": _z(publish_to),
        },
        "sources": sources,
        "files": {
            FUELHH_FILE: {"sha256": fh_hash, "rows": fuelhh_row_count, "bytes": len(fuelhh_bytes)},
            WINDFOR_FILE: {
                "sha256": wf_hash,
                "rows": windfor_row_count,
                "bytes": len(windfor_bytes),
            },
        },
        "data_sha256": _sha256((fh_hash + wf_hash).encode()),
        "attribution": ATTRIBUTION,
        "licence_note": (
            "Third-party data subject to Elexon BMRS Data Licence Terms; NOT covered by this "
            "repository's MIT licence. Verify attribution wording against the current licence."
        ),
        "limitations": list(LIMITATIONS),
        "tool": {"name": "wind-forecast-intelligence", "version": tool_version},
    }
    if notice:
        manifest["notice"] = notice
    return manifest


def write_snapshot(
    directory: Path,
    fuelhh: FetchResult,
    windfor: FetchResult,
    *,
    delivery_start: date,
    delivery_end: date,
    publish_from: datetime,
    publish_to: datetime,
    tool_version: str,
) -> dict[str, Any]:
    """Write a snapshot atomically: files are staged first, then moved into place (manifest last)."""
    sources = [
        {
            "dataset": r.request.dataset,
            "endpoint": r.request.endpoint,
            "query": r.request.query,
            "url": r.request.url,
            "retrieved_at": _z(r.request.retrieved_at),
            "http_status": r.request.status,
            "rows_returned": r.request.row_count,
            "attempts": r.request.attempts,
        }
        for r in (fuelhh, windfor)
    ]
    fh_bytes, wf_bytes = encode_files(fuelhh.rows, windfor.rows)
    manifest = build_manifest(
        fuelhh_bytes=fh_bytes,
        windfor_bytes=wf_bytes,
        fuelhh_row_count=len(fuelhh.rows),
        windfor_row_count=len(windfor.rows),
        sources=sources,
        retrieved_at=max(fuelhh.request.retrieved_at, windfor.request.retrieved_at),
        delivery_start=delivery_start,
        delivery_end=delivery_end,
        publish_from=publish_from,
        publish_to=publish_to,
        is_synthetic=False,
        tool_version=tool_version,
    )
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory, prefix=".staging-") as staging:
        stage = Path(staging)
        (stage / FUELHH_FILE).write_bytes(fh_bytes)
        (stage / WINDFOR_FILE).write_bytes(wf_bytes)
        (stage / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for name in (FUELHH_FILE, WINDFOR_FILE, MANIFEST_FILE):
            os.replace(stage / name, directory / name)
    return manifest


def raw_from_rows(
    fuelhh_rows: Sequence[Mapping[str, Any]],
    windfor_rows: Sequence[Mapping[str, Any]],
    manifest: dict[str, Any],
) -> RawSnapshot:
    """Round-trip rows through the on-disk encoding so in-memory and on-disk data behave identically."""
    fh_bytes, wf_bytes = encode_files(fuelhh_rows, windfor_rows)
    return RawSnapshot(
        fuelhh_rows=_read_gz_csv(fh_bytes, FUELHH_COLUMNS),
        windfor_rows=_read_gz_csv(wf_bytes, WINDFOR_COLUMNS),
        manifest=manifest,
    )


def load_snapshot(directory: Path) -> RawSnapshot:
    """Load and verify a snapshot; raises on missing files, hash or row-count mismatch."""
    manifest_path = directory / MANIFEST_FILE
    if not manifest_path.is_file():
        raise SnapshotNotFoundError(f"no snapshot manifest at {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except ValueError as exc:
        raise SnapshotIntegrityError(f"manifest is not valid JSON: {exc}") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotIntegrityError(
            f"unsupported snapshot schema {manifest.get('schema_version')!r}"
        )

    blobs: dict[str, bytes] = {}
    for name in (FUELHH_FILE, WINDFOR_FILE):
        path = directory / name
        if not path.is_file():
            raise SnapshotNotFoundError(f"snapshot file missing: {path}")
        blobs[name] = path.read_bytes()
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if _sha256(blobs[name]) != expected:
            raise SnapshotIntegrityError(f"checksum mismatch for {name}")
    combined = _sha256(
        (
            manifest["files"][FUELHH_FILE]["sha256"] + manifest["files"][WINDFOR_FILE]["sha256"]
        ).encode()
    )
    if combined != manifest.get("data_sha256"):
        raise SnapshotIntegrityError("combined data checksum mismatch")

    fh = _read_gz_csv(blobs[FUELHH_FILE], FUELHH_COLUMNS)
    wf = _read_gz_csv(blobs[WINDFOR_FILE], WINDFOR_COLUMNS)
    for name, rows in ((FUELHH_FILE, fh), (WINDFOR_FILE, wf)):
        if len(rows) != manifest["files"][name]["rows"]:
            raise SnapshotIntegrityError(f"row count mismatch for {name}")
    return RawSnapshot(fh, wf, manifest)
