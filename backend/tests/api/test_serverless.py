"""Serverless-readiness tests: lazy dataset loading and deployment-config consistency (Vercel)."""

from __future__ import annotations

import importlib.util
import json
import re
import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repository.datasets import LoadedData, SyntheticRepository

ROOT = Path(__file__).resolve().parents[3]


def test_dataset_loads_lazily_when_lifespan_never_runs() -> None:
    """Serverless hosts may not run ASGI lifespan: a TestClient NOT used as a context manager does the same."""
    client = TestClient(create_app(Settings(data_source_mode="synthetic"), SyntheticRepository()))
    r = client.get("/api/v1/analysis/summary")
    assert r.status_code == 200 and r.json()["provenance"]["is_synthetic"] is True
    assert client.get("/api/v1/health").json()["data_loaded"] is True


def test_failed_load_is_reported_then_recovers_on_a_later_request() -> None:
    class Flaky:
        calls = 0

        def load(self) -> LoadedData:
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise OSError("snapshot temporarily unreadable")
            return SyntheticRepository().load()

    client = TestClient(create_app(Settings(), Flaky()))
    first = client.get("/api/v1/meta")
    assert first.status_code == 503 and first.json()["error"]["code"] == "DATA_UNAVAILABLE"
    assert "snapshot temporarily unreadable" in first.json()["error"]["message"]
    assert (
        client.get("/api/v1/meta").status_code == 200
    )  # retried, no silent substitute data in between


def test_requirements_txt_matches_the_lockfile() -> None:
    """The Vercel function installs requirements.txt; it must pin exactly what uv.lock pins."""
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text())
    locked = {p["name"].lower().replace("_", "-"): p["version"] for p in lock["package"]}
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)(?:\s*;.*)?", line.strip())
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    assert pins, "requirements.txt has no pinned packages"
    for name, version in pins.items():
        assert locked.get(name) == version, (
            f"{name}: requirements.txt {version} != uv.lock {locked.get(name)}"
        )
    for needed in ("fastapi", "pandas", "numpy", "pydantic-settings", "httpx"):
        assert needed in pins
    assert "pytest" not in pins and "ruff" not in pins  # runtime only


def test_vercel_config_bundles_the_snapshot_and_routes_api_and_spa() -> None:
    cfg = json.loads((ROOT / "vercel.json").read_text())
    fn = cfg["functions"]["api/index.py"]
    assert "data/snapshots/**" in fn["includeFiles"] and "backend/app/**" in fn["includeFiles"]
    sources = [r["source"] for r in cfg["rewrites"]]
    assert sources[0] == "/api/(.*)" and cfg["rewrites"][0]["destination"] == "/api/index"
    assert cfg["outputDirectory"] == "frontend/dist" and "npm run build" in cfg["buildCommand"]
    assert any(
        r["destination"] == "/index.html" for r in cfg["rewrites"]
    )  # SPA fallback comes after the API rule
    csp = next(
        h["value"]
        for blk in cfg["headers"]
        for h in blk["headers"]
        if h["key"] == "Content-Security-Policy"
    )
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert (ROOT / "data" / "snapshots" / "manifest.json").is_file()


def test_vercel_entrypoint_exposes_the_asgi_app() -> None:
    spec = importlib.util.spec_from_file_location("vercel_api_index", ROOT / "api" / "index.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "app") and mod.app.title.startswith("UK Wind Forecast")
