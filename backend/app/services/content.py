"""Static, human-authored content exposed by the API (never computed, always dated and sourced)."""

from __future__ import annotations

APP_VERSION = "0.1.0"

PURPOSE = (
    "Retrospective simulation of historical day-ahead decision-making for January 2026 deliveries: "
    "which wind forecast could have been known at the decision cutoff, and how accurate was it? "
    "It is not a live forecast feed and does not give purchase recommendations."
)

ERROR_CONVENTION = (
    "error = actual generation - forecast generation (MW). Positive: actual exceeded the forecast "
    "(under-forecast). Negative: actual was below the forecast (over-forecast)."
)

CUTOFF_PRESETS = [
    {
        "id": "n2ex_0950",
        "label": "09:50 (provisional default)",
        "time": "09:50",
        "timezone": "Europe/London",
        "basis": (
            "Nord Pool support page for the N2EX day-ahead auction (modified 2022) gives gate closure "
            "09:50 GMT. Not confirmed as the relevant venue or still current in January 2026."
        ),
    },
    {
        "id": "epex_0920",
        "label": "09:20",
        "time": "09:20",
        "timezone": "Europe/London",
        "basis": "EPEX SPOT brochure snippets for a GB hourly day-ahead auction; primary source not verified.",
    },
    {
        "id": "epex_1530",
        "label": "15:30",
        "time": "15:30",
        "timezone": "Europe/London",
        "basis": "EPEX SPOT 2018 press release / secondary sources for a GB half-hourly day-ahead auction; unverified.",
    },
]

RESOLUTIONS = [
    {
        "id": "half_hour",
        "label": "30-minute (settlement periods)",
        "note": "Each hourly forecast is applied to both half-hours it covers. It is NOT an independent half-hour forecast.",
    },
    {
        "id": "hourly",
        "label": "Native hourly (forecast resolution)",
        "note": "Actual = mean of the two half-hours; an hour with a missing half-hour is unmatched (never filled).",
    },
]

ALIGNMENT_OPTIONS = [
    {
        "id": "start",
        "label": "Row covers the hour starting at startTime (assumed)",
        "status": "assumed",
        "note": "Chosen from the field name and Elexon's settlement-period labelling. Not verified by any official source.",
    },
    {
        "id": "end",
        "label": "Row covers the hour ending at startTime (sensitivity)",
        "status": "assumed",
        "note": "Provided only to show sensitivity. The default is not selected on error statistics.",
    },
]

CONFLICT_POLICIES = [
    {
        "id": "exclude",
        "label": "Exclude conflicted vintages",
        "note": "Conflicting records are removed (and listed). The next-latest clean vintage is used and flagged.",
    },
    {
        "id": "strict",
        "label": "Strict",
        "note": "If the latest eligible vintage is conflicted the interval is unavailable; no fallback.",
    },
]

DATASETS = [
    {
        "id": "FUELHH",
        "role": "Actual generation",
        "description": "Half-hourly generation outturn by fuel type; fuelType = WIND; average MW over 30 minutes.",
        "documentation": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream",
        "resolution": "30 minutes",
    },
    {
        "id": "WINDFOR",
        "role": "Forecast generation",
        "description": (
            "Wind generation forecast for wind farms visible to the ESO with operational metering; "
            "all published revisions retained with their original publishTime."
        ),
        "documentation": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream",
        "resolution": "60 minutes",
    },
]

SCOPE_DIAGNOSTIC = {
    "headline": "FUELHH WIND and WINDFOR may not cover the same generators.",
    "body": (
        "In a diagnostic comparison with another BMRS wind-actuals series (B1630, onshore + offshore), FUELHH WIND "
        "was about 2.2 GW lower on average and lower in 99.9% of half-hours (Oct 2025 - Jan 2026). Against that "
        "alternative series the same WINDFOR forecast had a January bias of +0.4 GW instead of -1.8 GW. "
        "Bias figures here therefore describe 'FUELHH versus WINDFOR' and should not be read as pure forecast skill. "
        "The cause is not established."
    ),
    "evidence": {
        "fuelhh_minus_b1630_mean_mw": -2249,
        "share_of_half_hours_fuelhh_below_b1630_pct": 99.9,
        "january_bias_vs_fuelhh_mw": -1840,
        "january_bias_vs_b1630_mw": 408,
        "january_mae_vs_fuelhh_mw": 2126,
        "january_mae_vs_b1630_mw": 1338,
    },
    "source": "docs/planning/04-data-research-notes.md section 10; reproducible with docs/planning/research/probe_bias_investigation.py",
    "measured_on": "2026-10-25 (static research finding, not computed by this application)",
    "not_established": [
        "What exactly FUELHH WIND and B1630 include (embedded vs transmission-connected, BM vs non-BM).",
        "What exactly WINDFOR covers beyond 'visible to the ESO with operational metering'.",
        "How much of the residual is genuine forecast error, and any curtailment effects.",
    ],
}

ASSUMPTIONS = [
    "Delivery date = Europe/London settlement date; all instants are handled in UTC.",
    "Decision cutoff = clock time on (delivery date minus days_before) in the cutoff time zone. Presets are configurable assumptions, not verified market deadlines.",
    "A forecast is eligible if publishTime <= cutoff - availability lag and it pre-dates the hour it describes; the latest eligible vintage is used.",
    "publishTime is treated as the moment a forecast became usable (availability lag defaults to 0).",
    "UNVERIFIED: a WINDFOR row stamped T describes the hour starting at T (alternative shown as a sensitivity).",
    "WINDFOR is hourly; in the 30-minute view one forecast value is shared by two half-hours.",
    "Units are MW (average power over the interval); FUELHH states average MW over 30 minutes.",
    "Missing values are never replaced by zero; metrics use only matched intervals and coverage is reported alongside.",
    "The Insights API serves one FUELHH value per interval; later corrections are not observable.",
]
