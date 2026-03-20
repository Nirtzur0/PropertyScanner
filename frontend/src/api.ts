import type {
  AgentRun,
  BenchmarkRun,
  CollectionResponse,
  CompReview,
  CompReviewWorkspaceResponse,
  CoverageReport,
  DataQualityEvent,
  JobRun,
  LayersResponse,
  ListingContextResponse,
  Memo,
  PipelineStatusResponse,
  PipelineTrustSummaryResponse,
  SavedSearch,
  SourceAuditResponse,
  SourceContractRun,
  UIEventPayload,
  Watchlist,
  WorkbenchFilters,
  WorkbenchResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";
const API_PREFIX = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function queryString(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "" || Number.isNaN(value)) {
      return;
    }
    search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  health: () => request<{ status: string; app: string; db_path: string }>(`${API_PREFIX}/health`),
  explore: (filters: WorkbenchFilters) =>
    request<WorkbenchResponse>(
      `${API_PREFIX}/workbench/explore${queryString({
        country: filters.country,
        city: filters.city,
        listing_type: filters.listing_type,
        min_price: filters.min_price,
        max_price: filters.max_price,
        min_support: filters.min_support,
        source_status: filters.source_status,
        search: filters.search,
        min_lat: filters.min_lat,
        max_lat: filters.max_lat,
        min_lon: filters.min_lon,
        max_lon: filters.max_lon,
        sort: filters.sort,
        limit: filters.limit,
        offset: filters.offset,
      })}`,
    ),
  listingContext: (listingId: string) =>
    request<ListingContextResponse>(`${API_PREFIX}/workbench/listings/${listingId}/context`),
  layers: () => request<LayersResponse>(`${API_PREFIX}/workbench/layers`),
  compReviewWorkspace: (listingId: string) =>
    request<CompReviewWorkspaceResponse>(`${API_PREFIX}/comp-reviews/${listingId}/workspace`),
  pipeline: () => request<PipelineStatusResponse>(`${API_PREFIX}/pipeline-status`),
  pipelineTrustSummary: () => request<PipelineTrustSummaryResponse>(`${API_PREFIX}/pipeline/trust-summary`),
  sources: () => request<SourceAuditResponse>(`${API_PREFIX}/sources`),
  jobs: () => request<CollectionResponse<JobRun>>(`${API_PREFIX}/job-runs`),
  benchmarks: () => request<CollectionResponse<BenchmarkRun>>(`${API_PREFIX}/benchmarks`),
  coverage: () => request<CollectionResponse<CoverageReport>>(`${API_PREFIX}/coverage-reports`),
  quality: () => request<CollectionResponse<DataQualityEvent>>(`${API_PREFIX}/data-quality-events`),
  sourceContracts: () => request<CollectionResponse<SourceContractRun>>(`${API_PREFIX}/source-contract-runs`),
  watchlists: () => request<CollectionResponse<Watchlist>>(`${API_PREFIX}/watchlists`),
  createWatchlist: (payload: {
    name: string;
    description?: string | null;
    status?: string;
    listing_ids: string[];
    filters: Record<string, string | number | boolean | null | undefined>;
    notes?: string | null;
  }) =>
    request<Watchlist>(`${API_PREFIX}/watchlists`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  savedSearches: () => request<CollectionResponse<SavedSearch>>(`${API_PREFIX}/saved-searches`),
  createSavedSearch: (payload: {
    name: string;
    query?: string | null;
    filters: Record<string, string | number | boolean | null | undefined>;
    sort: Record<string, string | number | boolean | null | undefined>;
    notes?: string | null;
  }) =>
    request<SavedSearch>(`${API_PREFIX}/saved-searches`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  memos: () => request<CollectionResponse<Memo>>(`${API_PREFIX}/memos`),
  createMemo: (payload: {
    title: string;
    listing_id?: string | null;
    watchlist_id?: string | null;
    status?: string;
    assumptions?: string[];
    risks?: string[];
    sections?: Array<{ heading: string; body: string }>;
    export_format?: string;
  }) =>
    request<Memo>(`${API_PREFIX}/memos`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  exportMemo: (memoId: string) =>
    request<{ memo_id: string; format: string; content: string }>(`${API_PREFIX}/memos/${memoId}/export`, { method: "POST" }),
  createValuation: (payload: { listing_id: string; persist: boolean }) =>
    request<{ listing_id: string; market_signals: Record<string, number> }>(`${API_PREFIX}/valuations`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  compReviews: (listingId?: string) =>
    request<CollectionResponse<CompReview>>(
      `${API_PREFIX}/comp-reviews${queryString({ listing_id: listingId })}`,
    ),
  createCompReview: (payload: {
    listing_id: string;
    status?: string;
    selected_comp_ids: string[];
    rejected_comp_ids: string[];
    overrides: Record<string, string | number | boolean | null>;
    notes?: string;
  }) =>
    request<CompReview>(`${API_PREFIX}/comp-reviews`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  commandRuns: () => request<CollectionResponse<AgentRun>>(`${API_PREFIX}/command-center/runs`),
  track: (payload: UIEventPayload) =>
    request<{ id: string; status: string }>(`${API_PREFIX}/ui-events`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
