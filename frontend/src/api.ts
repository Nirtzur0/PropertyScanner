import type {
  CollectionResponse,
  LayersResponse,
  ListingContextResponse,
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
  health: () => request<Record<string, unknown>>(`${API_PREFIX}/health`),
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
  pipeline: () => request<Record<string, unknown>>(`${API_PREFIX}/pipeline-status`),
  sources: () => request<Record<string, unknown>>(`${API_PREFIX}/sources`),
  jobs: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/job-runs`),
  benchmarks: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/benchmarks`),
  coverage: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/coverage-reports`),
  quality: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/data-quality-events`),
  watchlists: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/watchlists`),
  createWatchlist: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${API_PREFIX}/watchlists`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  savedSearches: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/saved-searches`),
  createSavedSearch: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${API_PREFIX}/saved-searches`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  memos: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/memos`),
  createMemo: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${API_PREFIX}/memos`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  exportMemo: (memoId: string) =>
    request<Record<string, unknown>>(`${API_PREFIX}/memos/${memoId}/export`, { method: "POST" }),
  createValuation: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${API_PREFIX}/valuations`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  compReviews: (listingId?: string) =>
    request<CollectionResponse<Record<string, unknown>>>(
      `${API_PREFIX}/comp-reviews${queryString({ listing_id: listingId })}`,
    ),
  createCompReview: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${API_PREFIX}/comp-reviews`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  commandRuns: () => request<CollectionResponse<Record<string, unknown>>>(`${API_PREFIX}/command-center/runs`),
};
