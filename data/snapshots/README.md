# Pinned Elexon data snapshot (REAL data)

| | |
|---|---|
| Source | Elexon BMRS **Insights Solution API**, `https://data.elexon.co.uk/bmrs/api/v1` (no API key) |
| Datasets | `FUELHH` (`fuelType=WIND`, half-hourly actual outturn) and `WINDFOR` (hourly wind forecast vintages) |
| Delivery period | settlement dates 2026-01-01 … 2026-01-31 |
| WINDFOR publish window | 2025-12-27T00:00Z … 2026-02-04T00:00Z (all forecast revisions in the window, original `publishTime` preserved) |
| Retrieved | see `manifest.json` → `retrieved_at` (UTC) |
| Rows | FUELHH 1,488 · WINDFOR 22,776 (312 vintages × 73 hourly rows) |
| Size | ≈ 127 KB (gzip CSV) |
| Integrity | SHA-256 of each file and a combined hash in `manifest.json`; verified on every load |
| Real or synthetic? | **REAL.** `is_synthetic: false`. (Development fixtures are generated in code and are always labelled synthetic.) |

Files hold the **verbatim API rows** (sorted by `startTime`, `publishTime`), so duplicate/conflict detection and all other normalisation run at load time and stay observable.

## Licence and attribution
This data is Elexon material and is **not** covered by this repository's MIT licence (see `/NOTICE`).
Attribution: *Contains BMRS data (c) Elexon Limited copyright and database right.*
The attribution wording was taken from secondary sources because Elexon's licence page blocked automated access; **verify against the current BMRS Data Licence Terms before publishing**. Elexon gives no warranty of accuracy.

## Limitations
See `manifest.json` → `limitations` and `docs/planning/04-data-research-notes.md` (§4, §9, §10). In particular: FUELHH `WIND` and WINDFOR may not cover identical generators, WINDFOR is hourly, and its hour alignment is an unverified assumption.

## Refresh / verify
```bash
cd backend
uv run python -m app.cli verify-snapshot          # integrity check only
uv run python -m app.cli ingest                    # re-fetch from Elexon (overwrites atomically; fails safe)
```
