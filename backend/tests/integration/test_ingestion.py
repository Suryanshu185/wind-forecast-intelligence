"""Ingestion client + snapshot tests. HTTP is mocked; payloads are SYNTHETIC unless noted."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.cli import main as cli_main
from app.ingestion.elexon_client import (
    ElexonClient,
    ElexonHTTPError,
    ElexonSchemaError,
    ElexonTimeoutError,
)
from app.ingestion.snapshot import (
    MANIFEST_FILE,
    SnapshotIntegrityError,
    SnapshotNotFoundError,
    load_snapshot,
    write_snapshot,
)

BASE = "https://elexon.test/api/v1"
FUEL_ROW = {
    "dataset": "FUELHH",
    "publishTime": "2026-01-01T00:30:00Z",
    "startTime": "2026-01-01T00:00:00Z",
    "settlementDate": "2026-01-01",
    "settlementPeriod": 1,
    "fuelType": "WIND",
    "generation": 1000,
}
WIND_ROW = {
    "dataset": "WINDFOR",
    "publishTime": "2025-12-31T22:30:00Z",
    "startTime": "2026-01-01T00:00:00Z",
    "generation": 1100,
}


def client(**kw: object) -> ElexonClient:
    sleeps: list[float] = []
    c = ElexonClient(BASE, sleep=sleeps.append, backoff_base=1.0, **kw)  # type: ignore[arg-type]
    c.sleeps = sleeps  # type: ignore[attr-defined]
    return c


@respx.mock
def test_fetch_fuelhh_builds_documented_query_and_records_provenance() -> None:
    route = respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        return_value=httpx.Response(200, json=[FUEL_ROW])
    )
    res = client().fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 31))
    q = route.calls.last.request.url.params
    assert q["settlementDateFrom"] == "2026-01-01" and q["settlementDateTo"] == "2026-01-31"
    assert q["fuelType"] == "WIND"
    assert res.rows == [FUEL_ROW]
    assert res.request.row_count == 1 and res.request.attempts == 1 and res.request.status == 200


@respx.mock
def test_fetch_windfor_uses_publish_window_in_utc_z() -> None:
    route = respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(
        return_value=httpx.Response(200, json=[WIND_ROW])
    )
    client().fetch_windfor(datetime(2025, 12, 27, tzinfo=UTC), datetime(2026, 2, 4, tzinfo=UTC))
    q = route.calls.last.request.url.params
    assert q["publishDateTimeFrom"] == "2025-12-27T00:00:00Z"
    assert q["publishDateTimeTo"] == "2026-02-04T00:00:00Z"


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        client().fetch_windfor(datetime(2025, 12, 27), datetime(2026, 2, 4))


@respx.mock
def test_429_honours_retry_after_then_succeeds() -> None:
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=[FUEL_ROW]),
        ]
    )
    c = client()
    res = c.fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))
    assert c.sleeps == [7.0]  # type: ignore[attr-defined]
    assert res.request.attempts == 2


@respx.mock
def test_500_then_success_uses_exponential_backoff() -> None:
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        side_effect=[httpx.Response(500), httpx.Response(503), httpx.Response(200, json=[FUEL_ROW])]
    )
    c = client()
    c.fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))
    assert c.sleeps == [1.0, 2.0]  # type: ignore[attr-defined]


@respx.mock
def test_persistent_500_raises_http_error_after_retries() -> None:
    route = respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(ElexonHTTPError) as ei:
        client(max_retries=2).fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))
    assert ei.value.status_code == 500 and route.call_count == 3


@respx.mock
def test_400_is_not_retried() -> None:
    route = respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        return_value=httpx.Response(400, text="bad date")
    )
    with pytest.raises(ElexonHTTPError) as ei:
        client().fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))
    assert ei.value.status_code == 400 and route.call_count == 1


@respx.mock
def test_timeout_after_retries_raises_timeout_error() -> None:
    route = respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(
        side_effect=httpx.ConnectTimeout("slow")
    )
    with pytest.raises(ElexonTimeoutError):
        client(max_retries=1).fetch_windfor(
            datetime(2025, 12, 27, tzinfo=UTC), datetime(2026, 2, 4, tzinfo=UTC)
        )
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b'[{"startTime": "2026-01-01T00:00'),  # truncated JSON
        httpx.Response(200, json={"data": []}),  # wrong shape (object, not array)
        httpx.Response(200, json=[1, 2, 3]),  # array of non-objects
    ],
)
def test_bad_payloads_raise_schema_error(response: httpx.Response) -> None:
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(return_value=response)
    with pytest.raises(ElexonSchemaError):
        client().fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))


@respx.mock
def test_empty_array_is_valid_and_reported_as_zero_rows() -> None:
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(return_value=httpx.Response(200, json=[]))
    res = client().fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1))
    assert res.rows == [] and res.request.row_count == 0


# ----------------------------------------------------------------------------- snapshot
def _fetch_both() -> tuple:
    with respx.mock:
        respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
            return_value=httpx.Response(
                200,
                json=[
                    FUEL_ROW,
                    {
                        **FUEL_ROW,
                        "generation": None,
                        "startTime": "2026-01-01T00:30:00Z",
                        "settlementPeriod": 2,
                    },
                ],
            )
        )
        respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(
            return_value=httpx.Response(200, json=[WIND_ROW])
        )
        c = client()
        pf, pt = datetime(2025, 12, 27, tzinfo=UTC), datetime(2026, 2, 4, tzinfo=UTC)
        return (
            c.fetch_fuelhh_wind(date(2026, 1, 1), date(2026, 1, 1)),
            c.fetch_windfor(pf, pt),
            pf,
            pt,
        )


def _write(tmp: Path) -> dict:
    fh, wf, pf, pt = _fetch_both()
    return write_snapshot(
        tmp,
        fh,
        wf,
        delivery_start=date(2026, 1, 1),
        delivery_end=date(2026, 1, 1),
        publish_from=pf,
        publish_to=pt,
        tool_version="test",
    )


def test_snapshot_roundtrip_preserves_values_including_null(tmp_path: Path) -> None:
    manifest = _write(tmp_path)
    snap = load_snapshot(tmp_path)
    assert snap.manifest == manifest
    assert snap.windfor_rows == [WIND_ROW]
    gens = {r["startTime"]: r["generation"] for r in snap.fuelhh_rows}
    assert (
        gens["2026-01-01T00:00:00Z"] == 1000 and gens["2026-01-01T00:30:00Z"] is None
    )  # null stays null
    assert manifest["is_synthetic"] is False
    assert manifest["files"]["windfor.csv.gz"]["rows"] == 1
    assert {s["dataset"] for s in manifest["sources"]} == {"FUELHH", "WINDFOR"}
    assert "attribution" in manifest and manifest["limitations"]


def test_snapshot_is_byte_reproducible(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a), _write(b)
    for name in ("fuelhh_wind.csv.gz", "windfor.csv.gz"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_tampered_file_is_detected(tmp_path: Path) -> None:
    _write(tmp_path)
    p = tmp_path / "windfor.csv.gz"
    p.write_bytes(p.read_bytes()[:-5] + b"xxxxx")
    with pytest.raises(SnapshotIntegrityError):
        load_snapshot(tmp_path)


def test_missing_snapshot_and_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SnapshotNotFoundError):
        load_snapshot(tmp_path)
    _write(tmp_path)
    (tmp_path / "windfor.csv.gz").unlink()
    with pytest.raises(SnapshotNotFoundError):
        load_snapshot(tmp_path)


def test_manifest_hash_edit_is_detected(tmp_path: Path) -> None:
    _write(tmp_path)
    mp = tmp_path / MANIFEST_FILE
    m = json.loads(mp.read_text())
    m["data_sha256"] = "0" * 64
    mp.write_text(json.dumps(m))
    with pytest.raises(SnapshotIntegrityError):
        load_snapshot(tmp_path)


@respx.mock
def test_failed_ingest_leaves_existing_snapshot_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    monkeypatch.setenv("ELEXON_BASE_URL", BASE)
    monkeypatch.setenv("ELEXON_MAX_RETRIES", "0")
    from app.config import get_settings

    get_settings.cache_clear()
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        return_value=httpx.Response(200, json=[FUEL_ROW])
    )
    respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(return_value=httpx.Response(500))
    rc = cli_main(
        ["ingest", "--start", "2026-01-01", "--end", "2026-01-01", "--out", str(tmp_path)]
    )
    get_settings.cache_clear()
    assert rc == 2
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert before == after
    assert not any(p.name.startswith(".staging-") for p in tmp_path.iterdir())
