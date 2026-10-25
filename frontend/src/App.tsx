import * as Tabs from "@radix-ui/react-tabs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Activity, BookOpenText, Gauge, LineChart, Wind } from "lucide-react";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { retryPolicy, useMeta, useSummary } from "@/api/hooks";
import { ProvenanceBadge, ScopeBanner, WarningList } from "@/components/banners";
import { AsyncPanel } from "@/components/states";
import { cn } from "@/lib/cn";
import { useAnalysisParams, useSelectedInterval, useTab, type TabId } from "@/lib/use-params";
import { AccuracyPanel } from "@/features/accuracy/AccuracyPanel";
import { ControlBar } from "@/features/controls/ControlBar";
import { DecisionPanel } from "@/features/decision/DecisionPanel";
import { ExplorerPanel } from "@/features/explorer/ExplorerPanel";
import { DataStrip } from "@/features/methodology/DataStrip";
import { MethodologyPage } from "@/features/methodology/MethodologyPage";

function Header() {
  const meta = useMeta();
  const link = ({ isActive }: { isActive: boolean }) =>
    cn("rounded-md px-3 py-1.5 text-sm transition-colors", isActive ? "bg-raised text-ink" : "text-muted hover:text-ink");
  return (
    <header className="border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-[88rem] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-actual/15 text-actual"><Wind className="size-4.5" aria-hidden /></span>
          <span>
            <span className="block text-[15px] font-semibold leading-tight tracking-tight">Wind Forecast Intelligence</span>
            <span className="block text-[11px] leading-tight text-muted">Retrospective day-ahead evaluation · January 2026 · GB</span>
          </span>
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-1">
          <NavLink to="/" end className={link}>Dashboard</NavLink>
          <NavLink to="/methodology" className={link}>Data &amp; methodology</NavLink>
        </nav>
        <ProvenanceBadge provenance={meta.data?.provenance} />
      </div>
    </header>
  );
}

function Footer() {
  const meta = useMeta();
  return (
    <footer className="mt-10 border-t border-border">
      <div className="mx-auto max-w-[88rem] space-y-1 px-4 py-6 text-xs text-muted sm:px-6">
        <p data-testid="attribution">
          Data: Elexon BMRS Insights API (FUELHH, WINDFOR). Attribution as cited by a third-party catalogue: “
          {meta.data?.attribution ?? "Contains BMRS data © Elexon Limited copyright and database right"}”. Elexon’s official licence wording has not been verified.
        </p>
        <p>
          Retrospective analysis of historical data for demonstration purposes. Not a live forecast and not purchase advice. Third-party data remain subject to Elexon’s licence terms.
        </p>
      </div>
    </footer>
  );
}

function Dashboard() {
  const [params, update] = useAnalysisParams();
  const meta = useMeta();
  const summary = useSummary(params);
  const [, setSelected] = useSelectedInterval();
  const [tab, setTab] = useTab();

  const tabCls =
    "inline-flex items-center gap-2 border-b-2 border-transparent px-3 py-2.5 text-sm text-muted transition-colors hover:text-ink data-[state=active]:border-actual data-[state=active]:text-ink";

  return (
    <div className="flex flex-col gap-4">
      <ControlBar params={params} onChange={update} meta={meta.data} />
      <ScopeBanner meta={meta.data} />
      <AsyncPanel query={summary} skeletonClassName="h-28" label="Loading data basis">
        {(s) => (
          <div className="flex flex-col gap-3">
            <DataStrip summary={s} />
            <WarningList warnings={s.warnings} hide={["SCOPE_MISMATCH"]} />
          </div>
        )}
      </AsyncPanel>

      <Tabs.Root value={tab} onValueChange={(v) => setTab(v as TabId)}>
        <Tabs.List aria-label="Analysis views" className="mb-4 flex flex-wrap border-b border-border">
          <Tabs.Trigger value="explorer" className={tabCls}><LineChart className="size-4" aria-hidden /> Forecast Explorer</Tabs.Trigger>
          <Tabs.Trigger value="accuracy" className={tabCls}><Gauge className="size-4" aria-hidden /> Accuracy analytics</Tabs.Trigger>
          <Tabs.Trigger value="decision" className={tabCls}><Activity className="size-4" aria-hidden /> Decision intelligence <span className="rounded bg-raised px-1.5 text-[10px] text-muted">scenarios</span></Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="explorer" className="outline-none"><ExplorerPanel params={params} /></Tabs.Content>
        <Tabs.Content value="accuracy" className="outline-none">
          <AccuracyPanel params={params} onInspect={(s) => { setSelected(s); setTab("explorer"); }} />
        </Tabs.Content>
        <Tabs.Content value="decision" className="outline-none"><DecisionPanel params={params} /></Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function NotFound() {
  return (
    <div className="py-16 text-center">
      <BookOpenText className="mx-auto mb-3 size-6 text-muted" aria-hidden />
      <p className="text-sm text-muted">Page not found. <Link className="underline" to="/">Back to the dashboard</Link></p>
    </div>
  );
}

/** Routes + chrome without providers (tests supply their own router / query client). */
export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-raised focus:px-3 focus:py-2">Skip to content</a>
      <Header />
      <main id="main" className="mx-auto w-full max-w-[88rem] flex-1 px-4 py-6 sm:px-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: retryPolicy } } });

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
