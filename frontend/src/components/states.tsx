import type { UseQueryResult } from "@tanstack/react-query";
import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { ApiClientError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function Skeleton({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={cn("animate-pulse rounded-lg bg-raised/70", className)}>
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error instanceof ApiClientError ? error : null;
  const waking = e ? e.status === 0 || e.status >= 502 : false;
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-over/40 bg-over/5 p-4">
      <div className="flex items-start gap-2 text-sm text-ink">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-over" aria-hidden />
        <div>
          <p className="font-medium">Could not load this panel</p>
          <p className="mt-1 text-muted">{e ? e.message : "An unexpected error occurred."}</p>
          {e && e.details.length > 0 ? (
            <ul className="mt-1 list-disc pl-5 text-xs text-muted">
              {e.details.map((d, i) => (
                <li key={i}>{d.field ? `${d.field}: ` : ""}{d.message}</li>
              ))}
            </ul>
          ) : null}
          {waking ? (
            <p className="mt-2 text-xs text-muted">
              If the service was idle it may still be starting up (can take about a minute on free hosting). Retry shortly.
            </p>
          ) : null}
        </div>
      </div>
      {onRetry && (!e || e.retryable) ? (
        <Button onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden /> Retry
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border p-8 text-center">
      <Inbox className="size-6 text-muted" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {children ? <div className="max-w-md text-sm text-muted">{children}</div> : null}
    </div>
  );
}

/**
 * Uniform loading / error / empty / content handling for every data panel.
 * While refetching with previous data on screen a subtle "Updating" indicator is shown.
 */
export function AsyncPanel<T>({
  query,
  children,
  isEmpty,
  empty,
  skeletonClassName = "h-64",
  label,
}: {
  query: UseQueryResult<T, unknown>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  skeletonClassName?: string;
  label?: string;
}) {
  if (query.isPending && !query.data) return <Skeleton className={skeletonClassName} label={label ?? "Loading"} />;
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const data = query.data as T;
  if (isEmpty?.(data)) return <>{empty ?? <EmptyState title="No data for this selection" />}</>;
  return (
    <div className="relative" aria-busy={query.isFetching}>
      {query.isFetching ? (
        <div role="status" className="absolute right-0 top-0 z-10 flex items-center gap-1 rounded-md bg-raised/90 px-2 py-1 text-xs text-muted">
          <Loader2 className="size-3 animate-spin" aria-hidden /> Updating
        </div>
      ) : null}
      {query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
      {children(data)}
    </div>
  );
}
