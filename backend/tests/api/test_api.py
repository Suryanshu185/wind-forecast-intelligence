"""API tests: contract, validation, error envelope, failure modes, determinism."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.domain.models import (
    ActualRecord,
    Conflict,
    ForecastRecord,
    NormalisationReport,
    NormalisedActuals,
    NormalisedForecasts,
)
from app.main import create_app
from app.repository.datasets import LoadedData, Provenance, SyntheticRepository


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


class StubRepository:
    """Hand-built dataset. Provenance is flagged synthetic because the values are invented."""

    def __init__(
        self,
        actuals: list[ActualRecord],
        forecasts: list[ForecastRecord],
        conflicts: list[Conflict] | None = None,
    ):
        self._a, self._f, self._c = actuals, forecasts, conflicts or []

    def load(self) -> LoadedData:
        manifest = {
            "period_covered": {"delivery_start": "2026-01-01", "delivery_end": "2026-01-31"},
            "sources": [{"dataset": "STUB"}],
            "attribution": "stub",
            "licence_note": "stub",
            "limitations": ["stub"],
            "notice": "SYNTHETIC test stub",
            "is_synthetic": True,
        }
        return LoadedData(
            NormalisedActuals(self._a, [], NormalisationReport("FUELHH")),
            NormalisedForecasts(self._f, self._c, NormalisationReport("WINDFOR")),
            Provenance("synthetic", True, utc(2026, 1, 1), "0" * 64, manifest),
        )


class BrokenRepository:
    def load(self) -> LoadedData:
        raise RuntimeError("snapshot exploded")


@pytest.fixture(scope="module")
def real() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as c:  # pinned REAL snapshot
        yield c


@pytest.fixture(scope="module")
def synthetic() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_source_mode="synthetic"), SyntheticRepository())) as c:
        yield c


def stub_client(
    actuals: list[ActualRecord],
    forecasts: list[ForecastRecord],
    conflicts: list[Conflict] | None = None,
):  # type: ignore[no-untyped-def]
    return TestClient(create_app(Settings(), StubRepository(actuals, forecasts, conflicts)))


def j(resp: Any) -> dict[str, Any]:
    assert "NaN" not in resp.text and "Infinity" not in resp.text, "non-finite number in JSON"
    return resp.json()  # type: ignore[no-any-return]


# ------------------------------------------------------------------ health / meta / availability
def test_health_and_meta(real: TestClient) -> None:
    assert j(real.get("/api/v1/health")) == {"status": "ok", "data_loaded": True, "detail": None}
    meta = j(real.get("/api/v1/meta"))
    assert meta["permitted_window"] == {"start": "2026-01-01", "end": "2026-01-31"}
    assert meta["defaults"]["cutoff_time"] == "09:50" and meta["defaults"]["days_before"] == 1
    assert (
        meta["defaults"]["resolution"] == "half_hour"
        and meta["defaults"]["hour_alignment"] == "start"
    )
    assert {p["time"] for p in meta["cutoff_presets"]} == {"09:50", "09:20", "15:30"}
    assert all(p["status"] == "configurable_assumption" for p in meta["cutoff_presets"])
    assert all(a["status"] == "assumed" for a in meta["alignment_options"])
    assert meta["provenance"]["is_synthetic"] is False and meta["provenance"]["mode"] == "snapshot"
    assert "Elexon" in meta["attribution"] and "error = actual" in meta["error_convention"]
    assert "may not cover the same generators" in meta["scope_diagnostic"]["headline"]


def test_unavailable_dataset_gives_503_and_degraded_health() -> None:
    with TestClient(create_app(Settings(), BrokenRepository())) as c:
        h = j(c.get("/api/v1/health"))
        assert (
            h["status"] == "degraded"
            and h["data_loaded"] is False
            and "snapshot exploded" in h["detail"]
        )
        r = c.get("/api/v1/analysis/summary")
        assert r.status_code == 503 and j(r)["error"]["code"] == "DATA_UNAVAILABLE"


def test_missing_snapshot_directory_is_a_503_not_a_silent_fallback(tmp_path: Any) -> None:
    with TestClient(
        create_app(Settings(data_source_mode="snapshot", data_snapshot_dir=tmp_path))
    ) as c:
        r = c.get("/api/v1/meta")
        assert r.status_code == 503 and "SnapshotNotFoundError" in j(r)["error"]["message"]


# ------------------------------------------------------------------ summary (real data)
def test_summary_default_matches_independent_probe_and_discloses_denominators(
    real: TestClient,
) -> None:
    s = j(real.get("/api/v1/analysis/summary"))
    c, m = s["counts"], s["metrics"]
    assert (c["expected"], c["matched"], c["coverage"], c["coverage_level"]) == (
        1488,
        1488,
        1.0,
        "ok",
    )
    assert (
        c["unit"] == "half-hour settlement periods"
        and s["counts_by_resolution"]["hourly"]["expected"] == 744
    )
    assert m["mae"] == pytest.approx(2126, abs=1) and m["rmse"] == pytest.approx(2621, abs=1)
    assert m["bias"] == pytest.approx(-1840, abs=1) and m["n"] == 1488 and m["unit"] == "MW"
    assert (
        s["config"]["cutoff_time"] == "09:50" and s["config"]["cutoff_timezone"] == "Europe/London"
    )
    assert (
        s["cutoff"]["status"] == "configurable_assumption" and s["alignment"]["status"] == "assumed"
    )
    assert s["cutoff"]["first_cutoff_utc"] == "2025-12-31T09:50:00Z"
    assert len(s["daily"]) == 31 and all(d["expected"] == 48 for d in s["daily"])
    assert sum(b["count"] for b in s["distribution"]["bins"]) == 1488
    assert s["distribution"]["error_definition"].startswith("error = actual - forecast")
    assert len(s["under_forecasts"]) <= 10 and len(s["over_forecasts"]) == 10
    assert all(x["error_mw"] < 0 for x in s["over_forecasts"]) and all(
        x["error_mw"] > 0 for x in s["under_forecasts"]
    )
    codes = {w["code"] for w in s["warnings"]}
    assert {"ALIGNMENT_ASSUMED", "SCOPE_MISMATCH"} <= codes and "SYNTHETIC_DATA" not in codes


def test_cutoff_change_changes_results_and_is_echoed(real: TestClient) -> None:
    a = j(real.get("/api/v1/analysis/summary", params={"cutoff_time": "09:20"}))
    b = j(real.get("/api/v1/analysis/summary", params={"cutoff_time": "09:50"}))
    assert a["config"]["cutoff_time"] == "09:20" and a["metrics"]["mae"] != b["metrics"]["mae"]
    assert a["metrics"]["mae"] == pytest.approx(2145, abs=1)


def test_date_subrange_resolution_and_alignment_params(real: TestClient) -> None:
    s = j(
        real.get(
            "/api/v1/analysis/summary",
            params={
                "delivery_start": "2026-01-10",
                "delivery_end": "2026-01-12",
                "resolution": "hourly",
                "hour_alignment": "end",
            },
        )
    )
    assert s["counts"]["expected"] == 72 and s["counts"]["unit"] == "hours"
    assert s["config"]["hour_alignment"] == "end" and "SENSITIVITY" in s["alignment"]["note"]
    assert len(s["daily"]) == 3


def test_availability_lag_param(real: TestClient) -> None:
    a = j(
        real.get(
            "/api/v1/analysis/summary",
            params={"cutoff_time": "09:50", "availability_lag_minutes": 21},
        )
    )
    b = j(real.get("/api/v1/analysis/summary", params={"cutoff_time": "09:50"}))
    assert (
        a["metrics"]["mae"] != b["metrics"]["mae"]
        and a["cutoff"]["description"].find("availability lag of 21 min") > 0
    )


# ------------------------------------------------------------------ validation & error envelope
@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"delivery_start": "2025-12-31"}, "OUT_OF_RANGE"),
        ({"delivery_end": "2026-02-01"}, "OUT_OF_RANGE"),
        ({"delivery_start": "2026-01-20", "delivery_end": "2026-01-10"}, "VALIDATION_ERROR"),
        ({"cutoff_time": "25:99"}, "VALIDATION_ERROR"),
        ({"cutoff_time": "abc"}, "VALIDATION_ERROR"),
        ({"days_before": 9}, "VALIDATION_ERROR"),
        ({"availability_lag_minutes": -1}, "VALIDATION_ERROR"),
        ({"resolution": "daily"}, "VALIDATION_ERROR"),
        ({"cutoff_timezone": "Mars/Base"}, "VALIDATION_ERROR"),
        ({"delivery_start": "not-a-date"}, "VALIDATION_ERROR"),
        ({"unknown_param": "1"}, "VALIDATION_ERROR"),
    ],
)
def test_invalid_requests_get_422_with_envelope(
    real: TestClient, params: dict[str, Any], code: str
) -> None:
    r = real.get("/api/v1/analysis/summary", params=params)
    body = j(r)
    assert r.status_code == 422 and body["error"]["code"] == code
    assert body["error"]["message"] and isinstance(body["error"]["details"], list)


def test_unknown_route_uses_error_envelope(real: TestClient) -> None:
    r = real.get("/api/v1/nope")
    assert r.status_code == 404 and j(r)["error"]["code"] == "NOT_FOUND"


def test_openapi_documents_endpoints(real: TestClient) -> None:
    paths = j(real.get("/openapi.json"))["paths"]
    assert {
        "/api/v1/analysis/summary",
        "/api/v1/analysis/intervals",
        "/api/v1/data-quality",
        "/api/v1/uncertainty/scenarios",
    } <= set(paths)


def test_responses_are_deterministic_byte_for_byte(real: TestClient) -> None:
    a = real.get("/api/v1/analysis/summary", params={"cutoff_time": "12:00"})
    b = real.get("/api/v1/analysis/summary", params={"cutoff_time": "12:00"})
    assert a.content == b.content


# ------------------------------------------------------------------ synthetic provenance
def test_synthetic_data_is_loudly_labelled(synthetic: TestClient) -> None:
    meta = j(synthetic.get("/api/v1/meta"))
    assert (
        meta["provenance"]["is_synthetic"] is True and "SYNTHETIC" in meta["provenance"]["notice"]
    )
    s = j(synthetic.get("/api/v1/analysis/summary"))
    crit = [w for w in s["warnings"] if w["code"] == "SYNTHETIC_DATA"]
    assert crit and crit[0]["severity"] == "critical" and s["provenance"]["is_synthetic"] is True


# ------------------------------------------------------------------ intervals & missing data states
def test_intervals_real_data(real: TestClient) -> None:
    r = j(
        real.get(
            "/api/v1/analysis/intervals",
            params={"delivery_start": "2026-01-15", "delivery_end": "2026-01-15"},
        )
    )
    rows = r["intervals"]
    assert len(rows) == 48 and r["counts"]["expected"] == 48
    first = rows[0]
    assert first["start_utc"] == "2026-01-15T00:00:00Z" and first["start_local"].startswith(
        "2026-01-15T00:00:00"
    )
    assert first["status"] == "MATCHED" and first["error_mw"] == pytest.approx(
        first["actual_mw"] - first["forecast_mw"]
    )
    assert first["forecast_published_at"] <= first["cutoff_utc"] and first["lead_time_h"] > 0
    assert (
        rows[0]["forecast_row_start"] == rows[1]["forecast_row_start"]
    )  # hourly forecast shared by two half-hours


def forecasts_for_hour10(published: list[tuple[datetime, float | None]]) -> list[ForecastRecord]:
    return [ForecastRecord(utc(2026, 1, 2, 10), p, mw) for p, mw in published]


def test_unavailable_forecast_is_null_not_zero_and_reduces_coverage() -> None:
    actuals = [
        ActualRecord(utc(2026, 1, 2, 10), utc(2026, 1, 2, 10, 30), 1200.0, date(2026, 1, 2), 21)
    ]
    late_only = forecasts_for_hour10(
        [(utc(2026, 1, 2, 2, 30), 5000.0)]
    )  # published after the D-1 cutoff
    with stub_client(actuals, late_only) as c:
        s = j(
            c.get(
                "/api/v1/analysis/summary",
                params={"delivery_start": "2026-01-02", "delivery_end": "2026-01-02"},
            )
        )
        assert (
            s["counts"]["forecast_unavailable"] == 2 - 1 or s["counts"]["forecast_unavailable"] == 1
        )
        assert (
            s["counts"]["matched"] == 0 and s["metrics"]["mae"] is None and s["metrics"]["n"] == 0
        )
        assert {w["code"] for w in s["warnings"]} >= {"NO_MATCHED_INTERVALS", "SYNTHETIC_DATA"}
        rows = j(
            c.get(
                "/api/v1/analysis/intervals",
                params={"delivery_start": "2026-01-02", "delivery_end": "2026-01-02"},
            )
        )["intervals"]
        row = next(x for x in rows if x["start_utc"] == "2026-01-02T10:00:00Z")
        assert (
            row["status"] == "FORECAST_UNAVAILABLE"
            and row["forecast_mw"] is None
            and row["error_mw"] is None
        )
        assert row["actual_mw"] == 1200.0 and row["unavailable_reason"] == "no_eligible_forecast"
        assert row["vintages_after_cutoff"] == 1


def test_missing_actual_zero_actual_and_partial_coverage_states() -> None:
    f = forecasts_for_hour10([(utc(2026, 1, 1, 7, 30), 1000.0)])
    actuals = [
        ActualRecord(
            utc(2026, 1, 2, 10), utc(2026, 1, 2, 10, 30), 0.0, date(2026, 1, 2), 21
        ),  # real zero
        ActualRecord(
            utc(2026, 1, 2, 10, 30), utc(2026, 1, 2, 11), None, date(2026, 1, 2), 22
        ),  # missing
    ]
    with stub_client(actuals, f) as c:
        p = {"delivery_start": "2026-01-02", "delivery_end": "2026-01-02"}
        rows = {
            x["start_utc"]: x for x in j(c.get("/api/v1/analysis/intervals", params=p))["intervals"]
        }
        zero, miss = rows["2026-01-02T10:00:00Z"], rows["2026-01-02T10:30:00Z"]
        assert (
            zero["status"] == "MATCHED" and zero["actual_mw"] == 0.0 and zero["error_mw"] == -1000.0
        )
        assert (
            miss["status"] == "ACTUAL_MISSING"
            and miss["actual_mw"] is None
            and miss["error_mw"] is None
        )
        s = j(c.get("/api/v1/analysis/summary", params=p))
        assert (
            s["counts"]["matched"] == 1
            and s["counts"]["actual_missing"] == 1
            and s["counts"]["coverage_level"] == "low"
        )
        assert any(
            w["code"] == "PARTIAL_DATA" and w["severity"] == "critical" for w in s["warnings"]
        )


def test_conflicts_are_visible_in_data_quality_and_flagged_in_summary() -> None:
    f = [ForecastRecord(utc(2026, 1, 2, 10), utc(2026, 1, 1, 7, 30), 1000.0)]
    conflicts = [
        Conflict("WINDFOR", utc(2026, 1, 2, 10), utc(2026, 1, 1, 9, 30), (1100.0, 1111.0), 2)
    ]
    acts = [
        ActualRecord(utc(2026, 1, 2, 10), utc(2026, 1, 2, 10, 30), 1200.0, date(2026, 1, 2), 21)
    ]
    with stub_client(acts, f, conflicts) as c:
        p = {"delivery_start": "2026-01-02", "delivery_end": "2026-01-02"}
        s = j(c.get("/api/v1/analysis/summary", params=p))
        assert s["counts"]["conflict_affected"] == 2 and any(
            w["code"] == "CONFLICTS" for w in s["warnings"]
        )
        dq = j(c.get("/api/v1/data-quality", params=p))
        assert dq["conflict_total"] == 1 and dq["conflicts"][0]["values_mw"] == [1100.0, 1111.0]
        strict = j(c.get("/api/v1/analysis/summary", params={**p, "conflict_policy": "strict"}))
        assert (
            strict["counts"]["forecast_unavailable"] == 1 and strict["counts"]["both_missing"] > 0
        )
        assert strict["metrics"]["n"] == 0  # the only actual has no usable forecast under strict


# ------------------------------------------------------------------ revisions
def test_revisions_explain_the_selection(real: TestClient) -> None:
    r = j(real.get("/api/v1/intervals/2026-01-10T10:00:00Z/revisions"))
    v = r["vintages"]
    assert [x["publish_utc"] for x in v] == sorted((x["publish_utc"] for x in v), reverse=True)
    selected = [x for x in v if x["selected"]]
    assert (
        len(selected) == 1
        and selected[0]["eligible"]
        and selected[0]["publish_utc"] == "2026-01-09T09:30:00Z"
    )
    after = [x for x in v if x["relative_to_cutoff_min"] > 0]
    assert after and all(
        (not x["eligible"] and "context only" in x["note"]) or "back-cast" in x["note"]
        for x in after
    )
    assert all(x["publish_utc"] <= r["cutoff_utc"] for x in v if x["eligible"])
    assert r["interval"]["start_utc"] == "2026-01-10T10:00:00Z" and len(r["explanation"]) >= 4
    assert any("Selected the latest eligible vintage" in line for line in r["explanation"])
    assert r["alignment"]["status"] == "assumed"
    sel_err = selected[0]["error_if_used_mw"]
    assert sel_err == pytest.approx(r["interval"]["error_mw"])


def test_revisions_for_unavailable_interval_say_so() -> None:
    acts = [
        ActualRecord(utc(2026, 1, 2, 10), utc(2026, 1, 2, 10, 30), 1200.0, date(2026, 1, 2), 21)
    ]
    with stub_client(acts, forecasts_for_hour10([(utc(2026, 1, 2, 2, 30), 5000.0)])) as c:
        r = j(
            c.get(
                "/api/v1/intervals/2026-01-02T10:00:00Z/revisions",
                params={"delivery_start": "2026-01-02", "delivery_end": "2026-01-02"},
            )
        )
        assert r["interval"]["status"] == "FORECAST_UNAVAILABLE" and not any(
            x["selected"] for x in r["vintages"]
        )
        assert any("UNAVAILABLE" in line for line in r["explanation"])


def test_revisions_errors(real: TestClient) -> None:
    out = real.get("/api/v1/intervals/2026-03-01T10:00:00Z/revisions")
    assert out.status_code == 404 and j(out)["error"]["code"] == "NOT_FOUND"
    naive = real.get("/api/v1/intervals/2026-01-10T10:00:00/revisions")
    assert naive.status_code == 422
    bad = real.get("/api/v1/intervals/garbage/revisions")
    assert bad.status_code == 422 and j(bad)["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------ scenarios & data quality
def test_scenarios_are_labelled_and_never_claim_money_or_volume(real: TestClient) -> None:
    r = real.get("/api/v1/uncertainty/scenarios", params={"include_rolling": "true"})
    s = j(r)
    assert "not a purchase or trading recommendation" in s["disclaimer"]
    buf = [b["buffer_mw"] for b in s["buffers"]]
    assert (
        [b["confidence_pct"] for b in s["buffers"]] == [50, 80, 90, 95]
        and buf == sorted(buf)
        and min(buf) >= 0
    )
    assert s["level_offset_mw"] == pytest.approx(-1840, abs=1) and s["error_std_mw"] > 0
    assert (
        len(s["by_hour_of_day"]) == 24
        and s["rolling_origin"]
        and s["sample"]["matched_intervals"] == 1488
    )
    text = r.text
    for denial in (
        s["disclaimer"],
        *s["caveats"],
    ):  # the product's own negations are allowed to name the words
        text = text.replace(denial, "")
    assert not any(
        tok in text.lower()
        for tok in ("£", "$", "€", "saving", "profit", "optimal", "purchase volume")
    )
    ro = s["rolling_origin"][0]
    assert ro["skipped_days"] >= 7 and ro["evaluated_days"] > 0


def test_scenarios_levels_validation(real: TestClient) -> None:
    ok = j(real.get("/api/v1/uncertainty/scenarios", params=[("levels", 60), ("levels", 99)]))
    assert [b["confidence_pct"] for b in ok["buffers"]] == [60, 99]
    assert real.get("/api/v1/uncertainty/scenarios", params={"levels": 100}).status_code == 422


def test_data_quality_reports_real_anomalies_and_counters(real: TestClient) -> None:
    dq = j(real.get("/api/v1/data-quality"))
    kinds = {a["type"] for a in dq["anomalies"]}
    assert {"OFF_SCHEDULE_VINTAGE", "MISSING_VINTAGE", "LATE_PUBLISHED_ACTUALS"} <= kinds
    assert any("2026-01-15" in str(a) for a in dq["anomalies"] if a["type"] == "MISSING_VINTAGE")
    assert (
        dq["normalisation"]["WINDFOR"]["accepted_rows"] == 22776
        and dq["normalisation"]["FUELHH"]["accepted_rows"] == 1488
    )
    assert dq["conflict_total"] == 0 and dq["vintage_stats"]["distinct_vintages_in_dataset"] == 312
    assert (
        dq["provenance"]["retrieved_at"]
        and dq["scope_diagnostic"]["evidence"]["january_bias_vs_b1630_mw"] == 408
    )
    assert dq["assumptions"] and dq["limitations"] and dq["sources"]


def test_responses_contain_only_json_serialisable_finite_numbers(real: TestClient) -> None:
    for path in (
        "/api/v1/analysis/summary",
        "/api/v1/analysis/intervals",
        "/api/v1/data-quality",
        "/api/v1/uncertainty/scenarios",
    ):
        json.loads(
            real.get(path).text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))
        )


def test_large_responses_are_gzip_compressed(real: TestClient) -> None:
    r = real.get("/api/v1/analysis/intervals", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and len(r.json()["intervals"]) == 1488


def test_security_headers_present(real: TestClient) -> None:
    h = real.get("/api/v1/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"


# ------------------------------------------------------------------ SPA serving (production image)
def test_spa_is_served_with_csp_and_path_traversal_is_blocked(tmp_path: Any) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("top secret")
    settings = Settings(frontend_dist_dir=dist)
    with TestClient(create_app(settings, SyntheticRepository())) as c:
        root = c.get("/")
        assert root.status_code == 200 and "<title>spa</title>" in root.text
        assert "default-src 'self'" in root.headers["content-security-policy"]
        assert c.get("/methodology").text == root.text  # client-side route falls back to index.html
        asset = c.get("/assets/app-abc123.js")
        assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
        assert "top secret" not in c.get("/../secret.txt").text
        assert "top secret" not in c.get("/%2e%2e/secret.txt").text
        assert c.get("/api/v1/health").status_code == 200  # API still takes precedence
        missing_api = c.get("/api/v1/does-not-exist")
        assert missing_api.status_code == 404 and missing_api.json()["error"]["code"] == "NOT_FOUND"
        assert "content-security-policy" not in c.get("/api/v1/health").headers


# ------------------------------------------------------------------ pre-release review: disclosure on every payload
def test_scope_notice_is_present_on_every_analytic_payload(real: TestClient) -> None:
    urls = [
        "/api/v1/analysis/summary",
        "/api/v1/analysis/intervals",
        "/api/v1/uncertainty/scenarios",
        "/api/v1/intervals/2026-01-10T10:00:00Z/revisions",
    ]
    for u in urls:
        body = j(real.get(u))
        assert "may not cover the same generators" in body["scope_notice"], u
        assert (
            "pure forecast skill" in body["scope_notice"] and "shortfall" in body["scope_notice"]
        ), u
    assert "scope_diagnostic" in j(real.get("/api/v1/data-quality")) and "scope_diagnostic" in j(
        real.get("/api/v1/meta")
    )


def test_attribution_is_flagged_unverified_and_never_called_official(real: TestClient) -> None:
    meta = j(real.get("/api/v1/meta"))
    assert meta["attribution"].startswith("Contains BMRS data")
    assert "Unverified" in meta["attribution_status"] and "official" in meta["attribution_status"]
    assert "Unverified" in meta["provenance"]["attribution_status"]
    assert (
        "NOT covered" in meta["provenance"]["licence_note"]
        or "not covered" in meta["provenance"]["licence_note"].lower()
    )


def test_scenarios_are_labelled_illustrative_and_not_trading_advice(real: TestClient) -> None:
    s = j(real.get("/api/v1/uncertainty/scenarios"))
    assert s["disclaimer"].startswith("Illustrative")
    assert "not a purchase or trading recommendation" in s["disclaimer"]


def test_every_cutoff_preset_is_a_labelled_assumption(real: TestClient) -> None:
    meta = j(real.get("/api/v1/meta"))
    assert all(p["status"] == "configurable_assumption" for p in meta["cutoff_presets"])
    s = j(real.get("/api/v1/analysis/summary"))
    assert (
        s["cutoff"]["status"] == "configurable_assumption"
        and "not a verified market deadline" in s["cutoff"]["description"]
    )
