"""Application service: validates requests, runs the pure analysis core (memoised) and shapes responses."""

from __future__ import annotations

import statistics
import threading
from collections import Counter, OrderedDict, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import Settings
from app.domain import scenarios as sc
from app.domain.analysis import (
    AnalysisConfig,
    AnalysisResult,
    Counts,
    Row,
    effective_cutoff,
    run_analysis,
)
from app.domain.calendar import LONDON, floor_hour, get_zone
from app.domain.metrics import Metrics, coverage_level
from app.domain.models import Conflict
from app.domain.selection import ForecastIndex
from app.repository.datasets import LoadedData
from app.schemas import models as m
from app.services import content

MAX_CONFLICTS_LISTED = 50
RESOLUTION_NOTES = {
    "half_hour": (
        "Hourly forecasts are applied to both half-hours they cover; they are NOT independent half-hour "
        "forecasts, and errors in adjacent half-hours are strongly dependent."
    ),
    "hourly": (
        "Native hourly resolution (the forecast's own resolution): actual = mean of the two half-hours in the "
        "hour; an hour with a missing half-hour is unmatched, never filled."
    ),
}
ALIGNMENT_NOTES = {
    "start": "ASSUMPTION (unverified): a WINDFOR row stamped T describes the hour starting at T.",
    "end": "SENSITIVITY (unverified): a WINDFOR row stamped T is treated as describing the hour ending at T.",
}


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 422,
        details: list[dict[str, str | None]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details or []


def _z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(dt: datetime) -> str:
    return dt.astimezone(LONDON).isoformat()


class AnalysisService:
    def __init__(self, data: LoadedData, settings: Settings, cache_size: int = 64) -> None:
        self.data, self.settings = data, settings
        self._cache: OrderedDict[AnalysisConfig, AnalysisResult] = OrderedDict()
        self._lock = threading.Lock()
        self._cache_size = cache_size
        self._index = ForecastIndex(data.forecasts.records, data.forecasts.conflicts)

    # ------------------------------------------------------------------ config & caching
    def default_config(self) -> AnalysisConfig:
        s = self.settings
        return AnalysisConfig(
            delivery_start=s.analysis_start_date,
            delivery_end=s.analysis_end_date,
            cutoff_time=s.decision_cutoff_time,
            cutoff_timezone=s.decision_timezone,
            days_before=s.decision_days_before_delivery,
            availability_lag_minutes=s.forecast_availability_lag_minutes,
            hour_alignment=s.hour_alignment,
            conflict_policy=s.duplicate_conflict_policy,
            resolution=s.analysis_resolution,
        )

    def resolve(self, q: m.AnalysisQuery) -> AnalysisConfig:
        d = self.default_config()
        lo, hi = self.settings.analysis_start_date, self.settings.analysis_end_date
        start, end = q.delivery_start or d.delivery_start, q.delivery_end or d.delivery_end
        for name, value in (("delivery_start", start), ("delivery_end", end)):
            if not lo <= value <= hi:
                raise ApiError(
                    "OUT_OF_RANGE",
                    f"{name} {value} is outside the permitted delivery window {lo} to {hi}.",
                    details=[{"field": name, "message": f"must be within {lo}..{hi}"}],
                )
        if start > end:
            raise ApiError(
                "VALIDATION_ERROR",
                "delivery_start must not be after delivery_end.",
                details=[{"field": "delivery_start", "message": "must be <= delivery_end"}],
            )
        tz = q.cutoff_timezone or d.cutoff_timezone
        try:
            get_zone(tz)
        except ValueError as exc:
            raise ApiError(
                "VALIDATION_ERROR",
                str(exc),
                details=[{"field": "cutoff_timezone", "message": str(exc)}],
            ) from exc

        def pick(v: Any, dv: Any) -> Any:
            return dv if v is None else v

        return AnalysisConfig(
            delivery_start=start,
            delivery_end=end,
            cutoff_time=(q.cutoff_time or d.cutoff_time).replace(second=0, microsecond=0),
            cutoff_timezone=tz,
            days_before=pick(q.days_before, d.days_before),
            availability_lag_minutes=pick(q.availability_lag_minutes, d.availability_lag_minutes),
            hour_alignment=pick(q.hour_alignment, d.hour_alignment),
            conflict_policy=pick(q.conflict_policy, d.conflict_policy),
            resolution=pick(q.resolution, d.resolution),
            top_k=pick(q.top_k, d.top_k),
            histogram_bin_mw=pick(q.histogram_bin_mw, d.histogram_bin_mw),
        )

    def analyse(self, cfg: AnalysisConfig) -> AnalysisResult:
        with self._lock:
            hit = self._cache.get(cfg)
            if hit is not None:
                self._cache.move_to_end(cfg)
                return hit
        result = run_analysis(self.data.actuals, self.data.forecasts, cfg)
        with self._lock:
            self._cache[cfg] = result
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    # ------------------------------------------------------------------ mapping helpers
    def provenance(self) -> m.ProvenanceOut:
        p, man = self.data.provenance, self.data.provenance.manifest
        return m.ProvenanceOut(
            mode=p.mode,
            is_synthetic=p.is_synthetic,
            retrieved_at=p.retrieved_at,
            data_sha256=p.data_sha256,
            period_covered=man["period_covered"],
            sources=man["sources"],
            attribution=content.ATTRIBUTION,
            attribution_status=content.ATTRIBUTION_STATUS,
            licence_note=man["licence_note"],
            limitations=man["limitations"],
            notice=man.get("notice"),
        )

    @staticmethod
    def resolved(cfg: AnalysisConfig) -> m.ResolvedConfig:
        return m.ResolvedConfig(
            delivery_start=cfg.delivery_start,
            delivery_end=cfg.delivery_end,
            cutoff_time=cfg.cutoff_time.strftime("%H:%M"),
            cutoff_timezone=cfg.cutoff_timezone,
            days_before=cfg.days_before,
            availability_lag_minutes=cfg.availability_lag_minutes,
            resolution=cfg.resolution,
            hour_alignment=cfg.hour_alignment,
            conflict_policy=cfg.conflict_policy,
            top_k=cfg.top_k,
            histogram_bin_mw=cfg.histogram_bin_mw,
        )

    @staticmethod
    def counts_out(c: Counts, resolution: str) -> m.CountsOut:
        return m.CountsOut(
            expected=c.expected,
            actual_observed=c.actual_observed,
            forecast_available=c.forecast_available,
            matched=c.matched,
            forecast_unavailable=c.forecast_unavailable,
            actual_missing=c.actual_missing,
            both_missing=c.both_missing,
            conflict_affected=c.conflict_affected,
            coverage=c.coverage,
            coverage_level=coverage_level(c.coverage),
            unit="half-hour settlement periods" if resolution == "half_hour" else "hours",
        )

    @staticmethod
    def metrics_out(x: Metrics) -> m.MetricsOut:
        return m.MetricsOut(
            n=x.n,
            mae=x.mae,
            rmse=x.rmse,
            bias=x.bias,
            p90_abs_error=x.p90_abs_error,
            error_std=x.error_std,
            mean_actual=x.mean_actual,
            mean_forecast=x.mean_forecast,
            nmae=x.nmae,
        )

    @staticmethod
    def interval_out(r: Row) -> m.IntervalOut:
        return m.IntervalOut(
            start_utc=r.start_utc,
            end_utc=r.end_utc,
            start_local=_local(r.start_utc),
            delivery_date=r.delivery_date,
            actual_mw=r.actual_mw,
            forecast_mw=r.forecast_mw,
            error_mw=r.error_mw,
            status=r.status,
            forecast_published_at=r.forecast_published_at,
            lead_time_h=r.lead_time_h,
            forecast_row_start=r.forecast_row_start,
            cutoff_utc=r.cutoff_utc,
            vintages_total=r.vintages_total,
            vintages_eligible=r.vintages_eligible,
            vintages_after_cutoff=r.vintages_after_cutoff,
            unavailable_reason=r.unavailable_reason,
            conflict_fallback=r.conflict_fallback,
            conflict_involved=r.conflict_involved,
            actual_conflict=r.actual_conflict,
        )

    @staticmethod
    def _alignment(cfg: AnalysisConfig) -> m.AlignmentInfo:
        return m.AlignmentInfo(value=cfg.hour_alignment, note=ALIGNMENT_NOTES[cfg.hour_alignment])

    @staticmethod
    def _cutoff_info(cfg: AnalysisConfig) -> m.CutoffInfo:
        first = effective_cutoff(cfg.delivery_start, cfg) + timedelta(
            minutes=cfg.availability_lag_minutes
        )
        lag = (
            f", minus an availability lag of {cfg.availability_lag_minutes} min"
            if cfg.availability_lag_minutes
            else ""
        )
        return m.CutoffInfo(
            description=(
                f"Decision cutoff = {cfg.cutoff_time:%H:%M} {cfg.cutoff_timezone} on the day "
                f"{cfg.days_before} day(s) before each delivery date{lag}. This is a configurable "
                "assumption, not a verified market deadline."
            ),
            first_delivery_date=cfg.delivery_start,
            first_cutoff_utc=first,
            first_cutoff_local=first.astimezone(get_zone(cfg.cutoff_timezone)).isoformat(),
        )

    def _warnings(self, cfg: AnalysisConfig, res: AnalysisResult) -> list[m.WarningOut]:
        w: list[m.WarningOut] = []
        if self.data.provenance.is_synthetic:
            w.append(
                m.WarningOut(
                    code="SYNTHETIC_DATA",
                    severity="critical",
                    message="These values are SYNTHETIC development data, not Elexon observations.",
                )
            )
        c = res.counts
        if c.expected and c.matched == 0:
            w.append(
                m.WarningOut(
                    code="NO_MATCHED_INTERVALS",
                    severity="critical",
                    message="No interval has both an actual and an eligible forecast; metrics are unavailable.",
                )
            )
        elif res.coverage_level in ("partial", "low"):
            w.append(
                m.WarningOut(
                    code="PARTIAL_DATA",
                    severity="critical" if res.coverage_level == "low" else "warning",
                    message=(
                        f"Only {c.matched} of {c.expected} expected intervals "
                        f"({100 * (c.coverage or 0):.1f}%) are matched; metrics cover those only."
                    ),
                )
            )
        if c.forecast_unavailable:
            w.append(
                m.WarningOut(
                    code="FORECAST_UNAVAILABLE",
                    severity="warning",
                    message=(
                        f"{c.forecast_unavailable} interval(s) have an actual but no forecast published by "
                        "the cutoff; they are shown as unavailable, not zero."
                    ),
                )
            )
        if c.conflict_affected:
            w.append(
                m.WarningOut(
                    code="CONFLICTS",
                    severity="warning",
                    message=(
                        f"{c.conflict_affected} interval(s) involve conflicting duplicate source records "
                        "(see data quality)."
                    ),
                )
            )
        if cfg.resolution == "hourly" and res.partial_hour_sps:
            w.append(
                m.WarningOut(
                    code="PARTIAL_HOURS",
                    severity="info",
                    message=(
                        f"{res.partial_hour_sps} half-hour(s) do not form a whole UTC hour and are excluded "
                        "from the hourly view."
                    ),
                )
            )
        w.append(
            m.WarningOut(
                code="ALIGNMENT_ASSUMED",
                severity="info",
                message=ALIGNMENT_NOTES[cfg.hour_alignment],
            )
        )
        w.append(
            m.WarningOut(
                code="SCOPE_MISMATCH",
                severity="warning",
                message=(
                    f"{content.SCOPE_DIAGNOSTIC['headline']} Measured differences may reflect dataset scope "
                    "as well as forecast performance."
                ),
            )
        )
        return w

    # ------------------------------------------------------------------ endpoints
    def meta(self) -> m.MetaOut:
        s = self.settings
        return m.MetaOut(
            app_version=content.APP_VERSION,
            purpose=content.PURPOSE,
            permitted_window={"start": s.analysis_start_date, "end": s.analysis_end_date},
            defaults=self.resolved(self.default_config()),
            cutoff_presets=[m.CutoffPreset(**p) for p in content.CUTOFF_PRESETS],
            resolutions=content.RESOLUTIONS,
            alignment_options=content.ALIGNMENT_OPTIONS,
            conflict_policies=content.CONFLICT_POLICIES,
            datasets=content.DATASETS,
            provenance=self.provenance(),
            attribution=content.ATTRIBUTION,
            attribution_status=content.ATTRIBUTION_STATUS,
            scope_diagnostic=content.SCOPE_DIAGNOSTIC,
            error_convention=content.ERROR_CONVENTION,
        )

    def summary(self, q: m.AnalysisQuery) -> m.SummaryOut:
        cfg = self.resolve(q)
        res = self.analyse(cfg)
        return m.SummaryOut(
            scope_notice=content.SCOPE_NOTICE,
            config=self.resolved(cfg),
            provenance=self.provenance(),
            alignment=self._alignment(cfg),
            cutoff=self._cutoff_info(cfg),
            resolution_note=RESOLUTION_NOTES[cfg.resolution],
            counts=self.counts_out(res.counts, cfg.resolution),
            counts_by_resolution={
                "half_hour": self.counts_out(res.counts_half_hour, "half_hour"),
                "hourly": self.counts_out(res.counts_hourly, "hourly"),
            },
            metrics=self.metrics_out(res.metrics),
            daily=[
                m.DailyOut(
                    delivery_date=x.delivery_date,
                    expected=x.counts.expected,
                    matched=x.counts.matched,
                    coverage=x.counts.coverage,
                    metrics=self.metrics_out(x.metrics),
                )
                for x in res.daily
            ],
            distribution=m.DistributionOut(
                bin_width_mw=cfg.histogram_bin_mw,
                bins=[
                    m.HistogramBinOut(lower_mw=b.lower, upper_mw=b.upper, count=b.count)
                    for b in res.histogram
                ],
                quantiles_mw=None
                if res.quantiles is None
                else {f"p{k}": v for k, v in res.quantiles.items()},
                over_forecast_count=res.over_forecast_count,
                under_forecast_count=res.under_forecast_count,
                exact_count=res.exact_count,
            ),
            under_forecasts=[self._extreme(x) for x in res.under_forecasts],
            over_forecasts=[self._extreme(x) for x in res.over_forecasts],
            elevated_days=res.elevated_days,
            lead_time_h=res.lead_time_h,
            vintages_used=res.vintages_used,
            warnings=self._warnings(cfg, res),
        )

    @staticmethod
    def _extreme(x: Any) -> m.ExtremeOut:
        return m.ExtremeOut(
            start_utc=x.start_utc,
            start_local=_local(x.start_utc),
            error_mw=x.error_mw,
            actual_mw=x.actual_mw,
            forecast_mw=x.forecast_mw,
        )

    def intervals(self, q: m.AnalysisQuery) -> m.IntervalsOut:
        cfg = self.resolve(q)
        res = self.analyse(cfg)
        return m.IntervalsOut(
            scope_notice=content.SCOPE_NOTICE,
            config=self.resolved(cfg),
            provenance=self.provenance(),
            alignment=self._alignment(cfg),
            resolution_note=RESOLUTION_NOTES[cfg.resolution],
            counts=self.counts_out(res.counts, cfg.resolution),
            intervals=[self.interval_out(r) for r in res.rows],
        )

    def revisions(self, start_utc: datetime, q: m.AnalysisQuery) -> m.RevisionsOut:
        if start_utc.tzinfo is None:
            raise ApiError(
                "VALIDATION_ERROR",
                "start_utc must carry a UTC offset (e.g. ...Z).",
                details=[{"field": "start_utc", "message": "naive timestamp"}],
            )
        start_utc = start_utc.astimezone(UTC)
        cfg = self.resolve(q)
        res = self.analyse(cfg)
        row = next((r for r in res.rows if r.start_utc == start_utc), None)
        if row is None:
            raise ApiError(
                "NOT_FOUND",
                f"No {cfg.resolution} interval starts at {_z(start_utc)} within the selected delivery range.",
                status=404,
            )
        hour_start = floor_hour(start_utc)
        stamp, cutoff = row.forecast_row_start, row.cutoff_utc
        vint: list[m.VintageOut] = []
        for v in reversed(self._index.vintages(stamp)):  # newest first
            eligible = v.publish_utc <= cutoff and v.publish_utc < hour_start and v.mw is not None
            selected = row.forecast_published_at == v.publish_utc and row.forecast_mw == v.mw
            if selected:
                note = "Selected: the latest vintage published at or before the cutoff."
            elif eligible:
                note = "Eligible at decision time, but superseded by a later eligible vintage."
            elif v.publish_utc >= hour_start:
                note = "Not usable: published after the delivery hour began (back-cast)."
            elif v.mw is None:
                note = "Not usable: no value in this vintage."
            else:
                note = "Not available at decision time (published after the cutoff). Shown for context only."
            vint.append(
                m.VintageOut(
                    publish_utc=v.publish_utc,
                    forecast_mw=v.mw,
                    lead_time_h=(hour_start - v.publish_utc).total_seconds() / 3600.0,
                    relative_to_cutoff_min=(v.publish_utc - cutoff).total_seconds() / 60.0,
                    eligible=eligible,
                    selected=selected,
                    error_if_used_mw=None
                    if row.actual_mw is None or v.mw is None
                    else row.actual_mw - v.mw,
                    note=note,
                )
            )
        conflicted = [
            c
            for c in self.data.forecasts.conflicts
            if c.dataset == "WINDFOR" and c.start_utc == stamp and c.publish_utc is not None
        ]
        return m.RevisionsOut(
            scope_notice=content.SCOPE_NOTICE,
            config=self.resolved(cfg),
            interval=self.interval_out(row),
            forecast_row_start=stamp,
            hour_start=hour_start,
            cutoff_utc=cutoff,
            vintages=vint,
            conflicted_vintages=[
                m.ConflictedVintageOut(
                    publish_utc=c.publish_utc,
                    values_mw=list(c.values),
                    row_count=c.row_count,
                )
                for c in conflicted
            ],
            explanation=self._explain(cfg, row),
            alignment=self._alignment(cfg),
        )

    @staticmethod
    def _explain(cfg: AnalysisConfig, row: Row) -> list[str]:
        tz = get_zone(cfg.cutoff_timezone)
        out = [
            f"Delivery date {row.delivery_date}; decision cutoff {_z(row.cutoff_utc)} "
            f"({row.cutoff_utc.astimezone(tz):%Y-%m-%d %H:%M} {cfg.cutoff_timezone}).",
            f"The forecast row consulted is WINDFOR startTime {_z(row.forecast_row_start)} "
            f"(alignment '{cfg.hour_alignment}' is an unverified assumption).",
            f"{row.vintages_total} vintage(s) exist for that row; {row.vintages_eligible} were published "
            f"at or before the cutoff and {row.vintages_after_cutoff} after it.",
        ]
        if row.forecast_mw is not None and row.forecast_published_at is not None:
            out.append(
                f"Selected the latest eligible vintage, published {_z(row.forecast_published_at)} "
                f"({row.lead_time_h or 0:.1f} h before the hour began): {row.forecast_mw:,.0f} MW."
            )
            if row.conflict_fallback:
                out.append(
                    "A newer vintage was conflicted (duplicate records disagreed) and was excluded."
                )
        elif row.unavailable_reason == "conflict":
            out.append(
                "No forecast is used: the latest eligible vintage has conflicting duplicate records."
            )
        else:
            out.append(
                "No forecast had been published by the cutoff, so it is UNAVAILABLE (not zero)."
            )
        if cfg.resolution == "half_hour":
            out.append("The same hourly forecast value applies to both half-hours of the hour.")
        if row.actual_mw is None:
            suffix = " (conflicting source records)." if row.actual_conflict else "."
            out.append("The actual is missing for this interval" + suffix)
        return out

    def scenarios(
        self, q: m.AnalysisQuery, include_rolling: bool, levels: list[int] | None
    ) -> m.ScenariosOut:
        cfg = self.resolve(q)
        res = self.analyse(cfg)
        lv = tuple(levels) if levels else sc.DEFAULT_LEVELS
        errors = [r.error_mw for r in res.rows if r.error_mw is not None]
        try:
            buffers = sc.underdelivery_buffers(errors, lv)
            bands = sc.error_bands(errors, lv)
        except ValueError as exc:
            raise ApiError(
                "VALIDATION_ERROR", str(exc), details=[{"field": "levels", "message": str(exc)}]
            ) from exc
        unit = "half-hour" if cfg.resolution == "half_hour" else "hour"
        hours_per_interval = 0.5 if cfg.resolution == "half_hour" else 1.0
        rolling: list[m.RollingOut] = []
        if include_rolling:
            for level in sorted(set(lv)):
                ro = sc.rolling_origin(res.rows, level)
                rolling.append(
                    m.RollingOut(
                        confidence_pct=level,
                        realised_pct=ro.realised_pct,
                        evaluated_days=len(ro.days),
                        skipped_days=ro.skipped_days,
                        days=[
                            m.RollingDayOut(
                                delivery_date=d.delivery_date,
                                history_days=d.history_days,
                                buffer_mw=d.buffer_mw,
                                n=d.n,
                                within_buffer=d.within_buffer,
                            )
                            for d in ro.days
                        ],
                    )
                )

        def bucket(xs: list[sc.Bucket]) -> list[m.BucketOut]:
            return [m.BucketOut(label=b.label, metrics=self.metrics_out(b.metrics)) for b in xs]

        return m.ScenariosOut(
            scope_notice=content.SCOPE_NOTICE,
            config=self.resolved(cfg),
            provenance=self.provenance(),
            disclaimer=sc.DISCLAIMER,
            caveats=[
                "Based on one winter month: about 31 days of strongly autocorrelated intervals, so the "
                "effective sample is far smaller than the interval count.",
                "In-sample: buffers describe what happened, not what will happen. The rolling-origin check "
                "is an out-of-sample test.",
                "Errors include the unexplained level offset between FUELHH and WINDFOR (see scope "
                "diagnostic); the offset is reported separately.",
                "Hourly forecasts are shared by two half-hours in the 30-minute view.",
                "No demand, contract, other-generation or price data are used; nothing here is a shortfall, "
                "volume, cost or saving.",
            ],
            sample={
                "matched_intervals": len(errors),
                "delivery_days": len(res.daily),
                "unit": unit,
            },
            level_offset_mw=res.metrics.bias,
            error_std_mw=res.metrics.error_std,
            buffers=[
                m.BufferOut(
                    confidence_pct=b.confidence_pct,
                    buffer_mw=b.buffer_mw,
                    raw_quantile_mw=b.raw_quantile_mw,
                    energy_mwh_per_interval_if_sustained=b.buffer_mw * hours_per_interval,
                )
                for b in buffers
            ],
            bands=[
                m.BandOut(confidence_pct=b.confidence_pct, lower_mw=b.lower_mw, upper_mw=b.upper_mw)
                for b in bands
            ],
            by_hour_of_day=bucket(sc.by_hour_of_day(res.rows)),
            by_lead_time=bucket(sc.by_lead_time(res.rows)),
            by_forecast_level=bucket(sc.by_forecast_level(res.rows)),
            elevated_days=res.elevated_days,
            rolling_origin=rolling,
            interval_unit=unit,
        )

    def data_quality(self, q: m.AnalysisQuery) -> m.DataQualityOut:
        cfg = self.resolve(q)
        res = self.analyse(cfg)
        d = self.data
        conflicts = [self._conflict_dict(c) for c in [*d.actuals.conflicts, *d.forecasts.conflicts]]
        return m.DataQualityOut(
            config=self.resolved(cfg),
            provenance=self.provenance(),
            sources=d.provenance.manifest["sources"],
            counts=self.counts_out(res.counts, cfg.resolution),
            counts_by_resolution={
                "half_hour": self.counts_out(res.counts_half_hour, "half_hour"),
                "hourly": self.counts_out(res.counts_hourly, "hourly"),
            },
            normalisation={
                "FUELHH": d.actuals.report.as_dict(),
                "WINDFOR": d.forecasts.report.as_dict(),
            },
            conflicts=conflicts[:MAX_CONFLICTS_LISTED],
            conflict_total=len(conflicts),
            vintage_stats=self._vintage_stats(res),
            anomalies=self._anomalies(),
            assumptions=content.ASSUMPTIONS,
            limitations=d.provenance.manifest["limitations"],
            scope_diagnostic=content.SCOPE_DIAGNOSTIC,
            partial_hour_sps=res.partial_hour_sps,
            unexpected_actual_rows=res.unexpected_actual_rows,
        )

    @staticmethod
    def _conflict_dict(c: Conflict) -> dict[str, object]:
        return {
            "dataset": c.dataset,
            "start_utc": _z(c.start_utc),
            "publish_utc": None if c.publish_utc is None else _z(c.publish_utc),
            "values_mw": list(c.values),
            "row_count": c.row_count,
        }

    def _vintage_stats(self, res: AnalysisResult) -> dict[str, object]:
        pubs = Counter(r.publish_utc for r in self.data.forecasts.records)
        return {
            "distinct_vintages_in_dataset": len(pubs),
            "first_publish_utc": _z(min(pubs)) if pubs else None,
            "last_publish_utc": _z(max(pubs)) if pubs else None,
            "typical_rows_per_vintage": statistics.mode(pubs.values()) if pubs else None,
            "distinct_vintages_selected_in_range": res.vintages_used,
            "selected_lead_time_h": res.lead_time_h,
        }

    def _anomalies(self) -> list[dict[str, object]]:
        """Data-derived observations only; the nominal publication schedule is never assumed."""
        out: list[dict[str, object]] = []
        pubs = sorted({r.publish_utc for r in self.data.forecasts.records})
        if pubs:
            by_day: dict[date, list[datetime]] = defaultdict(list)
            for p in pubs:
                by_day[p.date()].append(p)
            clock = Counter(p.strftime("%H:%M") for p in pubs)
            typical = sorted(t for t, n in clock.items() if n >= 0.5 * len(by_day))
            for t, n in sorted(clock.items()):
                if t not in typical:
                    when = [_z(p) for p in pubs if p.strftime("%H:%M") == t]
                    out.append(
                        {
                            "type": "OFF_SCHEDULE_VINTAGE",
                            "detail": f"Forecast published at {t}Z on {n} occasion(s), unlike the usual "
                            f"times {', '.join(typical)}Z.",
                            "instances": when[:10],
                        }
                    )
            for day in sorted(by_day):
                have = {p.strftime("%H:%M") for p in by_day[day]}
                gone = [t for t in typical if t not in have]
                if gone:
                    out.append(
                        {
                            "type": "MISSING_VINTAGE",
                            "detail": f"No forecast published at {', '.join(gone)}Z on {day}.",
                            "date": day.isoformat(),
                        }
                    )
        lags = {
            r.start_utc: (r.publish_utc - r.start_utc).total_seconds() / 60
            for r in self.data.actuals.records
        }
        if lags:
            usual = statistics.mode(lags.values())
            late = sorted((s, v) for s, v in lags.items() if v > usual)
            if late:
                out.append(
                    {
                        "type": "LATE_PUBLISHED_ACTUALS",
                        "detail": f"{len(late)} FUELHH interval(s) were published later than the usual "
                        f"{usual:.0f} min after the interval started (up to {max(v for _, v in late):.0f} min).",
                        "instances": [_z(s) for s, _ in late[:10]],
                    }
                )
        return out
