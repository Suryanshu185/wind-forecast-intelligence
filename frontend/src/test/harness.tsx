import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppShell } from "@/App";
import {
  makeDataQuality,
  makeIntervals,
  makeMeta,
  makeRevisions,
  makeScenarios,
  makeSummary,
} from "./fixtures.synthetic";

type Handler = (url: URL) => unknown | { __status: number; body?: unknown };
export type Handlers = Partial<Record<"meta" | "summary" | "intervals" | "revisions" | "scenarios" | "quality", Handler>>;

export const failWith = (status: number, code = "INTERNAL", message = "boom") => ({
  __status: status,
  body: { error: { code, message, details: [] } },
});

const defaults: Required<Handlers> = {
  meta: () => makeMeta(),
  summary: () => makeSummary(),
  intervals: () => makeIntervals(),
  revisions: () => makeRevisions(),
  scenarios: () => makeScenarios(),
  quality: () => makeDataQuality(),
};

/** Replace global fetch with a router over the API paths; returns the call log. */
export function mockApi(over: Handlers = {}) {
  const h = { ...defaults, ...over };
  const calls: URL[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    calls.push(url);
    const p = url.pathname;
    let handler: Handler | undefined;
    if (p.endsWith("/meta")) handler = h.meta;
    else if (p.endsWith("/analysis/summary")) handler = h.summary;
    else if (p.endsWith("/analysis/intervals")) handler = h.intervals;
    else if (p.endsWith("/revisions")) handler = h.revisions;
    else if (p.endsWith("/uncertainty/scenarios")) handler = h.scenarios;
    else if (p.endsWith("/data-quality")) handler = h.quality;
    if (!handler) return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "nope", details: [] } }), { status: 404 });
    const out = handler(url) as { __status?: number; body?: unknown };
    if (out && typeof out === "object" && "__status" in out) {
      return new Response(JSON.stringify(out.body ?? {}), { status: out.__status, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    byPath: (suffix: string) => calls.filter((u) => u.pathname.endsWith(suffix)),
  };
}

export function renderApp(route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <AppShell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
