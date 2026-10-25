"""HTTP routes (thin: validation + delegation to the service)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.schemas import models as m
from app.services.analysis_service import AnalysisService, ApiError

router = APIRouter(prefix="/api/v1")

Q = Annotated[m.AnalysisQuery, Query()]


def service_of(request: Request) -> AnalysisService:
    svc: AnalysisService | None = getattr(request.app.state, "service", None)
    if svc is None:
        detail = getattr(request.app.state, "load_error", "dataset not loaded")
        raise ApiError("DATA_UNAVAILABLE", f"The dataset is not available: {detail}", status=503)
    return svc


@router.get("/health", response_model=m.HealthOut, tags=["meta"])
def health(request: Request) -> m.HealthOut:
    loaded = getattr(request.app.state, "service", None) is not None
    return m.HealthOut(
        status="ok" if loaded else "degraded",
        data_loaded=loaded,
        detail=None
        if loaded
        else str(getattr(request.app.state, "load_error", "dataset not loaded")),
    )


@router.get("/meta", response_model=m.MetaOut, tags=["meta"])
def meta(request: Request) -> m.MetaOut:
    return service_of(request).meta()


@router.get("/analysis/summary", response_model=m.SummaryOut, tags=["analysis"])
def analysis_summary(request: Request, q: Q) -> m.SummaryOut:
    return service_of(request).summary(q)


@router.get("/analysis/intervals", response_model=m.IntervalsOut, tags=["analysis"])
def analysis_intervals(request: Request, q: Q) -> m.IntervalsOut:
    return service_of(request).intervals(q)


@router.get("/intervals/{start_utc}/revisions", response_model=m.RevisionsOut, tags=["analysis"])
def interval_revisions(request: Request, start_utc: datetime, q: Q) -> m.RevisionsOut:
    return service_of(request).revisions(start_utc, q)


@router.get("/uncertainty/scenarios", response_model=m.ScenariosOut, tags=["decision-intelligence"])
def uncertainty_scenarios(
    request: Request, q: Annotated[m.ScenariosQuery, Query()]
) -> m.ScenariosOut:
    return service_of(request).scenarios(q, q.include_rolling, q.levels)


@router.get("/data-quality", response_model=m.DataQualityOut, tags=["meta"])
def data_quality(request: Request, q: Q) -> m.DataQualityOut:
    return service_of(request).data_quality(q)
