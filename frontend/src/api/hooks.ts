import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { toApiQuery, type AnalysisParams } from "@/lib/params";
import { ApiClientError, getJson } from "./client";
import type { DataQuality, Intervals, Meta, Revisions, Scenarios, Summary } from "./types";

/** Retry only failures that can succeed on retry (network, 429, 5xx). Applied via the QueryClient defaults. */
export const retryPolicy = (failureCount: number, error: unknown) =>
  error instanceof ApiClientError ? error.retryable && failureCount < 2 : failureCount < 1;

const common = { staleTime: 5 * 60_000, refetchOnWindowFocus: false } as const;

export const useMeta = () =>
  useQuery({ queryKey: ["meta"], queryFn: ({ signal }) => getJson<Meta>("/api/v1/meta", signal), ...common });

export const useSummary = (p: AnalysisParams) =>
  useQuery({
    queryKey: ["summary", p],
    queryFn: ({ signal }) => getJson<Summary>(`/api/v1/analysis/summary?${toApiQuery(p)}`, signal),
    placeholderData: keepPreviousData,
    ...common,
  });

export const useIntervals = (p: AnalysisParams) =>
  useQuery({
    queryKey: ["intervals", p],
    queryFn: ({ signal }) => getJson<Intervals>(`/api/v1/analysis/intervals?${toApiQuery(p)}`, signal),
    placeholderData: keepPreviousData,
    ...common,
  });

export const useRevisions = (startUtc: string | null, p: AnalysisParams) =>
  useQuery({
    queryKey: ["revisions", startUtc, p],
    queryFn: ({ signal }) =>
      getJson<Revisions>(`/api/v1/intervals/${encodeURIComponent(startUtc as string)}/revisions?${toApiQuery(p)}`, signal),
    enabled: startUtc !== null,
    ...common,
  });

export const useScenarios = (p: AnalysisParams, enabled: boolean) =>
  useQuery({
    queryKey: ["scenarios", p],
    queryFn: ({ signal }) =>
      getJson<Scenarios>(`/api/v1/uncertainty/scenarios?${toApiQuery(p, { include_rolling: "true" })}`, signal),
    enabled,
    placeholderData: keepPreviousData,
    ...common,
  });

export const useDataQuality = (p: AnalysisParams) =>
  useQuery({
    queryKey: ["data-quality", p],
    queryFn: ({ signal }) => getJson<DataQuality>(`/api/v1/data-quality?${toApiQuery(p)}`, signal),
    placeholderData: keepPreviousData,
    ...common,
  });
