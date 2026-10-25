import { CalendarRange, ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import type { Meta } from "@/api/types";
import { Card } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/info-tip";
import { cn } from "@/lib/cn";
import { clampDate, WINDOW_END, WINDOW_START, type AnalysisParams } from "@/lib/params";

const PRESETS = [
  { label: "Whole month", from: "2026-01-01", to: "2026-01-31" },
  { label: "1–7 Jan", from: "2026-01-01", to: "2026-01-07" },
  { label: "8–14 Jan", from: "2026-01-08", to: "2026-01-14" },
  { label: "15–21 Jan", from: "2026-01-15", to: "2026-01-21" },
  { label: "22–28 Jan", from: "2026-01-22", to: "2026-01-28" },
  { label: "29–31 Jan", from: "2026-01-29", to: "2026-01-31" },
];

const FALLBACK_CUTOFFS = [
  { time: "09:50", label: "09:50 (provisional default)" },
  { time: "09:20", label: "09:20" },
  { time: "15:30", label: "15:30" },
];

const field = "h-9 rounded-md border border-border bg-bg px-2 text-sm text-ink";
const label = "mb-1 flex items-center gap-1 text-xs font-medium text-muted";

function Segmented<T extends string>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: Array<{ id: T; label: string }>;
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="inline-flex overflow-hidden rounded-md border border-border">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          onClick={() => onChange(o.id)}
          className={cn(
            "h-9 px-3 text-sm transition-colors",
            value === o.id ? "bg-actual/20 font-medium text-actual" : "bg-bg text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ControlBar({
  params,
  onChange,
  meta,
}: {
  params: AnalysisParams;
  onChange: (p: Partial<AnalysisParams>) => void;
  meta: Meta | undefined;
}) {
  const [dateError, setDateError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const uid = useId();
  const presets = meta?.cutoff_presets.map((p) => ({ time: p.time, label: p.label })) ?? FALLBACK_CUTOFFS;
  const isPreset = presets.some((p) => p.time === params.cutoff_time);

  function setDate(which: "delivery_start" | "delivery_end", value: string) {
    if (!value) return; // user is mid-edit; wait for a complete date
    const clamped = clampDate(value, which === "delivery_start" ? WINDOW_START : WINDOW_END);
    setDateError(
      clamped !== value || value < WINDOW_START || value > WINDOW_END
        ? "Delivery dates are limited to 1–31 January 2026; the value was adjusted."
        : null,
    );
    onChange({ [which]: clamped } as Partial<AnalysisParams>);
  }

  return (
    <Card aria-label="Analysis controls" className="p-4 sm:p-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[auto_auto_auto_auto_1fr]">
        <div>
          <span className={label}>
            <CalendarRange className="size-3.5" aria-hidden /> Delivery dates (January 2026 only)
          </span>
          <div className="flex items-center gap-2">
            <label className="sr-only" htmlFor={`${uid}-from`}>Delivery start date</label>
            <input
              id={`${uid}-from`}
              type="date"
              className={field}
              min={WINDOW_START}
              max={WINDOW_END}
              value={params.delivery_start}
              onChange={(e) => setDate("delivery_start", e.target.value)}
            />
            <span aria-hidden className="text-muted">→</span>
            <label className="sr-only" htmlFor={`${uid}-to`}>Delivery end date</label>
            <input
              id={`${uid}-to`}
              type="date"
              className={field}
              min={WINDOW_START}
              max={WINDOW_END}
              value={params.delivery_end}
              onChange={(e) => setDate("delivery_end", e.target.value)}
            />
          </div>
          {dateError ? (
            <p role="alert" className="mt-1 text-xs text-warn">{dateError}</p>
          ) : null}
        </div>

        <div>
          <label className={label} htmlFor={`${uid}-cutoff`}>
            Decision cutoff (Europe/London)
            <InfoTip label="About the decision cutoff">
              Forecasts published after this time on the decision day are ignored. Presets are configurable assumptions,
              not verified market deadlines.
            </InfoTip>
          </label>
          <div className="flex items-center gap-2">
            <select
              id={`${uid}-cutoff`}
              className={field}
              value={isPreset ? params.cutoff_time : "custom"}
              onChange={(e) => e.target.value !== "custom" && onChange({ cutoff_time: e.target.value })}
            >
              {presets.map((p) => (
                <option key={p.time} value={p.time}>{p.label}</option>
              ))}
              <option value="custom">Custom…</option>
            </select>
            <input
              aria-label="Cutoff time"
              type="time"
              className={cn(field, "w-[7.5rem]")}
              value={params.cutoff_time}
              onChange={(e) => /^\d{2}:\d{2}$/.test(e.target.value) && onChange({ cutoff_time: e.target.value })}
            />
          </div>
        </div>

        <div>
          <label className={label} htmlFor={`${uid}-days`}>
            Decision day
            <InfoTip label="About the decision day">
              Delivery date and decision date differ: a day-ahead decision for delivery date D is made on D−1.
            </InfoTip>
          </label>
          <select
            id={`${uid}-days`}
            className={field}
            value={params.days_before}
            onChange={(e) => onChange({ days_before: Number(e.target.value) })}
          >
            <option value={1}>Day-ahead (D−1)</option>
            <option value={2}>Two days ahead (D−2)</option>
            <option value={3}>Three days ahead (D−3)</option>
            <option value={0}>Same day (D)</option>
          </select>
        </div>

        <div>
          <label className={label} htmlFor={`${uid}-lag`}>
            Availability lag (min)
            <InfoTip label="About availability lag">
              Minutes between a forecast’s publishTime and when it could actually be used. Default 0.
            </InfoTip>
          </label>
          <input
            id={`${uid}-lag`}
            type="number"
            inputMode="numeric"
            min={0}
            max={720}
            step={5}
            className={cn(field, "w-24")}
            value={params.availability_lag_minutes}
            onChange={(e) => {
              const n = Math.max(0, Math.min(720, Math.trunc(Number(e.target.value) || 0)));
              onChange({ availability_lag_minutes: n });
            }}
          />
        </div>

        <div className="md:col-span-2 xl:col-span-1 xl:justify-self-end">
          <span className={label}>
            Comparison resolution
            <InfoTip label="About comparison resolution">
              WINDFOR forecasts are hourly; FUELHH actuals are half-hourly. In the 30-minute view each hourly forecast is
              shared by two half-hours. The native hourly view compares the mean of the two half-hours with the forecast.
            </InfoTip>
          </span>
          <Segmented
            name="Comparison resolution"
            value={params.resolution}
            onChange={(resolution) => onChange({ resolution })}
            options={[
              { id: "half_hour", label: "30-minute" },
              { id: "hourly", label: "Native hourly" },
            ]}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="Quick date ranges">
        {PRESETS.map((p) => {
          const active = params.delivery_start === p.from && params.delivery_end === p.to;
          return (
            <button
              key={p.label}
              type="button"
              aria-pressed={active}
              onClick={() => {
                setDateError(null);
                onChange({ delivery_start: p.from, delivery_end: p.to });
              }}
              className={cn(
                "h-8 rounded-full border px-3 text-xs transition-colors",
                active ? "border-actual/60 bg-actual/15 text-actual" : "border-border text-muted hover:text-ink",
              )}
            >
              {p.label}
            </button>
          );
        })}
        <button
          type="button"
          aria-expanded={advanced}
          aria-controls={`${uid}-adv`}
          onClick={() => setAdvanced((a) => !a)}
          className="ml-auto inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-muted hover:text-ink"
        >
          Assumptions &amp; sensitivity <ChevronDown className={cn("size-3.5 transition-transform", advanced && "rotate-180")} aria-hidden />
        </button>
      </div>

      {advanced ? (
        <div id={`${uid}-adv`} className="mt-3 grid gap-4 border-t border-border/70 pt-4 md:grid-cols-2">
          <fieldset>
            <legend className={label}>WINDFOR hour alignment — unverified assumption</legend>
            <Segmented
              name="Hour alignment"
              value={params.hour_alignment}
              onChange={(hour_alignment) => onChange({ hour_alignment })}
              options={[
                { id: "start", label: "Hour starting at startTime (assumed)" },
                { id: "end", label: "Hour ending at startTime (sensitivity)" },
              ]}
            />
            <p className="mt-1 text-xs text-muted">
              No official source states which hour a WINDFOR row describes. The default is not chosen on error statistics.
            </p>
          </fieldset>
          <fieldset>
            <legend className={label}>Conflicting duplicate source records</legend>
            <Segmented
              name="Conflict policy"
              value={params.conflict_policy}
              onChange={(conflict_policy) => onChange({ conflict_policy })}
              options={[
                { id: "exclude", label: "Exclude & flag" },
                { id: "strict", label: "Strict (unavailable)" },
              ]}
            />
            <p className="mt-1 text-xs text-muted">Conflicts are never silently resolved. None exist in the January 2026 snapshot.</p>
          </fieldset>
        </div>
      ) : null}
    </Card>
  );
}
