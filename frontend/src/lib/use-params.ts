import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { parseParams, toSearchParams, type AnalysisParams } from "@/lib/params";

/** Analysis configuration backed by the URL query string (sanitised on every read). */
export function useAnalysisParams(): [AnalysisParams, (patch: Partial<AnalysisParams>) => void] {
  const [sp, setSp] = useSearchParams();
  const params = useMemo(() => parseParams(sp), [sp]);
  const update = useCallback(
    (patch: Partial<AnalysisParams>) => {
      const next = { ...params, ...patch };
      if (next.delivery_start > next.delivery_end) {
        // keep the range valid: moving one end past the other drags the other end along
        if ("delivery_start" in patch) next.delivery_end = next.delivery_start;
        else next.delivery_start = next.delivery_end;
      }
      const out = toSearchParams(next);
      // preserve non-analysis params (e.g. selected interval)
      for (const [k, v] of sp.entries()) if (k === "at" || k === "tab") out.set(k, v);
      setSp(out, { replace: true });
    },
    [params, setSp, sp],
  );
  return [params, update];
}

/** Selected interval start (UTC ISO) kept in the URL as `at`. */
export function useSelectedInterval(): [string | null, (iso: string | null) => void] {
  const [sp, setSp] = useSearchParams();
  const at = sp.get("at");
  const set = useCallback(
    (iso: string | null) => {
      const next = new URLSearchParams(sp);
      if (iso) next.set("at", iso);
      else next.delete("at");
      setSp(next, { replace: true });
    },
    [sp, setSp],
  );
  return [at, set];
}

export type TabId = "explorer" | "accuracy" | "decision";

/** Active dashboard tab kept in the URL as `tab` (shareable links). */
export function useTab(): [TabId, (t: TabId) => void] {
  const [sp, setSp] = useSearchParams();
  const raw = sp.get("tab");
  const tab: TabId = raw === "accuracy" || raw === "decision" ? raw : "explorer";
  const set = useCallback(
    (t: TabId) => {
      const next = new URLSearchParams(sp);
      if (t === "explorer") next.delete("tab");
      else next.set("tab", t);
      setSp(next, { replace: true });
    },
    [sp, setSp],
  );
  return [tab, set];
}
