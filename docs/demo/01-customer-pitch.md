# Part 1 — Customer pitch (target 4:30, hard limit 5:00)

Audience: a UK utility's procurement team. Tone: credible, specific, honest about limits.
Run the app from the production build (`docker compose up --build`, or backend with `FRONTEND_DIST_DIR=../frontend/dist`) at 1440×900. Numbers below are from the pinned real snapshot at the default settings (09:50 Europe/London, D−1, 30-minute view); re-check them on screen before recording.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:30 | Dashboard, header + data strip | "Wind output moves by thousands of megawatts. A day-ahead buyer commits before delivery, so what matters is the forecast **at the moment of the decision** — not today's best forecast. This tool replays that decision for January 2026 using Elexon's official data. It is a retrospective simulation, not a live feed, and not purchase advice." Point at the green *Real Elexon BMRS data* badge and the *Data basis* strip (1,488 expected half-hours, 100 % matched). |
| 0:30–1:20 | Controls | "The decision cutoff is explicit and editable: 09:50 on the day before, London time. I'm labelling it an assumption — I found 09:50 documented for the N2EX auction, but I could not verify the current market deadline, so I don't claim it as fact." Switch to 09:20 and back (or open the dropdown). "Even 30 minutes matters here, because a forecast is published at 09:30." |
| 1:20–2:20 | Forecast Explorer → click a half-hour (e.g. 15 Jan 10:00 with range 15–16 Jan, cutoff 12:30) | "Teal is what actually generated; amber is the forecast that was available at the cutoff." Click an interval. "Here is exactly why that forecast: of 24 published versions, 13 were available by the cutoff; this is the latest of those. The later ones are shown only for context." Point at the revision chart with the cutoff line. "If no forecast existed, you'd see a hatched gap labelled *unavailable* — never a zero." |
| 2:20–3:30 | Accuracy tab | "Mean absolute error 2,126 MW, RMSE 2,621 MW, P90 4,368 MW, over 1,488 of 1,488 intervals — every number shows its denominator." Point at bias: "−1,840 MW: the forecast was on average above what FUELHH reports. **I want to be careful here**: I tested whether this is a unit error, a cutoff artefact or duplicates — it isn't. Against a different Elexon wind-outturn series, the same forecast is within about +400 MW. So much of this is a **dataset-scope** difference, and the app says so on every view rather than calling it forecast skill." Show daily trend (worst days 11–12 Jan, 28 Jan) and the largest-miss table. |
| 3:30–4:20 | Decision intelligence | "This is *scenario* analysis, labelled as such. From the month's errors: in 90 % of half-hours, wind was no more than about 4,300 MW below the forecast. I'm not telling you how much to buy — I don't have your demand, contracts or prices. And I tested the idea honestly: using only earlier days, the 50 % buffer held 45 % of the time — so it's rough." Scroll to *what it can and cannot show*. |
| 4:20–4:30 | Methodology page | "Every definition, assumption and known data anomaly is on this page. Thanks." |

## Safe claims (say these) / unsafe claims (don't)
- Safe: "forecast available at the cutoff", "over 1,488 matched half-hours", "reflects dataset scope as well as forecast performance", "one winter month".
- Unsafe: any £ saving, "optimal volume", "forecast is biased high" without the scope caveat, "09:50 is the market deadline".

## Pre-recording checklist
- [ ] Snapshot badge shows *Real Elexon BMRS data* (not SYNTHETIC).
- [ ] Browser zoom 100 %, window 1440×900, no personal bookmarks/tabs visible.
- [ ] Re-read each number on screen; adjust the script if anything differs.
- [ ] Total length under 5:00 for this part.
