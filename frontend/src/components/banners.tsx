import { Link } from "react-router-dom";
import { AlertOctagon, AlertTriangle, FlaskConical, Info, ShieldCheck } from "lucide-react";
import type { ApiWarning, Meta, Provenance } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { fmtRetrieved } from "@/lib/format";

const tone = {
  info: { box: "border-border bg-raised/50 text-muted", icon: Info },
  warning: { box: "border-warn/40 bg-warn/5 text-ink", icon: AlertTriangle },
  critical: { box: "border-over/50 bg-over/10 text-ink", icon: AlertOctagon },
} as const;

/** Server-generated warnings (partial data, unavailable forecasts, conflicts, synthetic data, assumptions). */
export function WarningList({ warnings, hide = [] }: { warnings: ApiWarning[]; hide?: string[] }) {
  const shown = warnings.filter((w) => !hide.includes(w.code));
  if (shown.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2" aria-label="Data warnings">
      {shown.map((w) => {
        const t = tone[w.severity];
        const Icon = t.icon;
        return (
          <li key={w.code} data-testid={`warning-${w.code}`} className={cn("flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] leading-snug", t.box)}>
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{w.message}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Always-visible statement of whether numbers are real Elexon data or a synthetic fixture. */
export function ProvenanceBadge({ provenance }: { provenance: Provenance | undefined }) {
  if (!provenance) return <Badge>Loading data provenance…</Badge>;
  if (provenance.is_synthetic) {
    return (
      <Badge tone="bad" data-testid="provenance-badge" title={provenance.notice ?? undefined}>
        <FlaskConical className="size-3" aria-hidden /> SYNTHETIC DEVELOPMENT FIXTURE — not Elexon data
      </Badge>
    );
  }
  return (
    <Badge tone="good" data-testid="provenance-badge">
      <ShieldCheck className="size-3" aria-hidden /> Real Elexon BMRS data · snapshot retrieved {fmtRetrieved(provenance.retrieved_at)}
    </Badge>
  );
}

/** The dataset-scope caveat: shown on every analytic view. */
export function ScopeBanner({ meta }: { meta: Meta | undefined }) {
  const s = meta?.scope_diagnostic;
  return (
    <aside
      aria-label="Dataset scope caveat"
      data-testid="scope-banner"
      className="flex items-start gap-2 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-[13px] leading-snug text-ink"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
      <p>
        <strong className="font-semibold">{s?.headline ?? "FUELHH WIND and WINDFOR may not cover the same generators."}</strong>{" "}
        Measured differences may reflect dataset scope as well as forecast performance — read bias as “FUELHH versus WINDFOR”, not pure forecast skill.{" "}
        <Link className="underline decoration-dotted underline-offset-2 hover:text-actual" to="/methodology#scope">
          Evidence and limits
        </Link>
      </p>
    </aside>
  );
}
