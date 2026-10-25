"""API request / response schemas (Pydantic v2). The public contract of the backend."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["MATCHED", "FORECAST_UNAVAILABLE", "ACTUAL_MISSING", "BOTH_MISSING"]
Resolution = Literal["half_hour", "hourly"]
Alignment = Literal["start", "end"]
ConflictPolicy = Literal["exclude", "strict"]


# --------------------------------------------------------------------------- request
class AnalysisQuery(BaseModel):
    """Query parameters shared by analytic endpoints. Unset fields fall back to server defaults."""

    model_config = ConfigDict(extra="forbid")

    delivery_start: date | None = Field(
        None, description="First delivery (settlement) date, inclusive."
    )
    delivery_end: date | None = Field(
        None, description="Last delivery (settlement) date, inclusive."
    )
    cutoff_time: time | None = Field(
        None, description="Decision cutoff clock time HH:MM in cutoff_timezone."
    )
    cutoff_timezone: str | None = Field(None, description="IANA zone for the cutoff clock time.")
    days_before: Annotated[int, Field(ge=0, le=3)] | None = Field(
        None, description="Decision day = delivery date minus this many days (1 = day-ahead)."
    )
    availability_lag_minutes: Annotated[int, Field(ge=0, le=720)] | None = None
    resolution: Resolution | None = None
    hour_alignment: Alignment | None = Field(
        None,
        description="ASSUMPTION (unverified): whether a WINDFOR row describes the hour starting or ending at startTime.",
    )
    conflict_policy: ConflictPolicy | None = None
    top_k: Annotated[int, Field(ge=1, le=50)] | None = None
    histogram_bin_mw: Annotated[float, Field(ge=50, le=5000)] | None = None


# --------------------------------------------------------------------------- shared
class ProvenanceOut(BaseModel):
    mode: str
    is_synthetic: bool
    retrieved_at: datetime
    data_sha256: str
    period_covered: dict[str, str]
    sources: list[dict[str, object]]
    attribution: str
    licence_note: str
    limitations: list[str]
    notice: str | None = None


class ResolvedConfig(BaseModel):
    delivery_start: date
    delivery_end: date
    cutoff_time: str
    cutoff_timezone: str
    days_before: int
    availability_lag_minutes: int
    resolution: Resolution
    hour_alignment: Alignment
    conflict_policy: ConflictPolicy
    top_k: int
    histogram_bin_mw: float


class AlignmentInfo(BaseModel):
    value: Alignment
    status: Literal["assumed"] = "assumed"
    note: str


class CutoffInfo(BaseModel):
    description: str
    first_delivery_date: date
    first_cutoff_utc: datetime
    first_cutoff_local: str
    status: Literal["configurable_assumption"] = "configurable_assumption"


class CountsOut(BaseModel):
    expected: int
    actual_observed: int
    forecast_available: int
    matched: int
    forecast_unavailable: int
    actual_missing: int
    both_missing: int
    conflict_affected: int
    coverage: float | None
    coverage_level: Literal["ok", "partial", "low", "undefined"]
    unit: Literal["half-hour settlement periods", "hours"]


class MetricsOut(BaseModel):
    n: int
    mae: float | None
    rmse: float | None
    bias: float | None
    p90_abs_error: float | None
    error_std: float | None
    mean_actual: float | None
    mean_forecast: float | None
    nmae: float | None
    unit: Literal["MW"] = "MW"


class WarningOut(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    message: str


# --------------------------------------------------------------------------- summary
class DailyOut(BaseModel):
    delivery_date: date
    expected: int
    matched: int
    coverage: float | None
    metrics: MetricsOut


class HistogramBinOut(BaseModel):
    lower_mw: float
    upper_mw: float
    count: int


class DistributionOut(BaseModel):
    bin_width_mw: float
    bins: list[HistogramBinOut]
    quantiles_mw: dict[str, float] | None
    over_forecast_count: int
    under_forecast_count: int
    exact_count: int
    error_definition: str = (
        "error = actual - forecast; negative = forecast above actual (over-forecast)"
    )


class ExtremeOut(BaseModel):
    start_utc: datetime
    start_local: str
    error_mw: float
    actual_mw: float
    forecast_mw: float


class SummaryOut(BaseModel):
    config: ResolvedConfig
    provenance: ProvenanceOut
    alignment: AlignmentInfo
    cutoff: CutoffInfo
    resolution_note: str
    counts: CountsOut
    counts_by_resolution: dict[str, CountsOut]
    metrics: MetricsOut
    daily: list[DailyOut]
    distribution: DistributionOut
    under_forecasts: list[ExtremeOut]
    over_forecasts: list[ExtremeOut]
    elevated_days: list[date]
    lead_time_h: dict[str, float] | None
    vintages_used: int
    warnings: list[WarningOut]


# --------------------------------------------------------------------------- intervals
class IntervalOut(BaseModel):
    start_utc: datetime
    end_utc: datetime
    start_local: str
    delivery_date: date
    actual_mw: float | None
    forecast_mw: float | None
    error_mw: float | None
    status: Status
    forecast_published_at: datetime | None
    lead_time_h: float | None
    forecast_row_start: datetime
    cutoff_utc: datetime
    vintages_total: int
    vintages_eligible: int
    vintages_after_cutoff: int
    unavailable_reason: str | None
    conflict_fallback: bool
    conflict_involved: bool
    actual_conflict: bool


class IntervalsOut(BaseModel):
    config: ResolvedConfig
    provenance: ProvenanceOut
    alignment: AlignmentInfo
    resolution_note: str
    counts: CountsOut
    intervals: list[IntervalOut]


class VintageOut(BaseModel):
    publish_utc: datetime
    forecast_mw: float | None
    lead_time_h: float
    relative_to_cutoff_min: float  # negative = published before the cutoff
    eligible: bool
    selected: bool
    error_if_used_mw: float | None
    note: str


class ConflictedVintageOut(BaseModel):
    publish_utc: datetime
    values_mw: list[float | None]
    row_count: int


class RevisionsOut(BaseModel):
    config: ResolvedConfig
    interval: IntervalOut
    forecast_row_start: datetime
    hour_start: datetime
    cutoff_utc: datetime
    vintages: list[VintageOut]
    conflicted_vintages: list[ConflictedVintageOut]
    explanation: list[str]
    alignment: AlignmentInfo


# --------------------------------------------------------------------------- scenarios
class BufferOut(BaseModel):
    confidence_pct: int
    buffer_mw: float
    raw_quantile_mw: float
    energy_mwh_per_interval_if_sustained: float


class BandOut(BaseModel):
    confidence_pct: int
    lower_mw: float
    upper_mw: float


class BucketOut(BaseModel):
    label: str
    metrics: MetricsOut


class RollingDayOut(BaseModel):
    delivery_date: date
    history_days: int
    buffer_mw: float
    n: int
    within_buffer: int


class RollingOut(BaseModel):
    confidence_pct: int
    realised_pct: float | None
    evaluated_days: int
    skipped_days: int
    days: list[RollingDayOut]


class ScenariosOut(BaseModel):
    config: ResolvedConfig
    provenance: ProvenanceOut
    disclaimer: str
    caveats: list[str]
    sample: dict[str, object]
    level_offset_mw: float | None
    error_std_mw: float | None
    buffers: list[BufferOut]
    bands: list[BandOut]
    by_hour_of_day: list[BucketOut]
    by_lead_time: list[BucketOut]
    by_forecast_level: list[BucketOut]
    elevated_days: list[date]
    rolling_origin: list[RollingOut]
    interval_unit: str


# --------------------------------------------------------------------------- data quality / meta
class DataQualityOut(BaseModel):
    config: ResolvedConfig
    provenance: ProvenanceOut
    sources: list[dict[str, object]]
    counts: CountsOut
    counts_by_resolution: dict[str, CountsOut]
    normalisation: dict[str, dict[str, object]]
    conflicts: list[dict[str, object]]
    conflict_total: int
    vintage_stats: dict[str, object]
    anomalies: list[dict[str, object]]
    assumptions: list[str]
    limitations: list[str]
    scope_diagnostic: dict[str, object]
    partial_hour_sps: int
    unexpected_actual_rows: int


class CutoffPreset(BaseModel):
    id: str
    label: str
    time: str
    timezone: str
    status: Literal["configurable_assumption"] = "configurable_assumption"
    basis: str


class MetaOut(BaseModel):
    app_version: str
    purpose: str
    permitted_window: dict[str, date]
    defaults: ResolvedConfig
    cutoff_presets: list[CutoffPreset]
    resolutions: list[dict[str, str]]
    alignment_options: list[dict[str, str]]
    conflict_policies: list[dict[str, str]]
    datasets: list[dict[str, str]]
    provenance: ProvenanceOut
    attribution: str
    scope_diagnostic: dict[str, object]
    error_convention: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    data_loaded: bool
    detail: str | None = None


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: Literal["VALIDATION_ERROR", "OUT_OF_RANGE", "NOT_FOUND", "DATA_UNAVAILABLE", "INTERNAL"]
    message: str
    details: list[ErrorDetail] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ScenariosQuery(AnalysisQuery):
    """Analysis parameters plus scenario-specific options."""

    include_rolling: bool = Field(
        False, description="Include the out-of-sample rolling-origin check."
    )
    levels: list[Annotated[int, Field(gt=0, lt=100)]] | None = Field(
        None, description="Confidence levels in percent (default 50, 80, 90, 95)."
    )
