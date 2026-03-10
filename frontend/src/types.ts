export type WorkbenchFilters = {
  country?: string;
  city?: string;
  listing_type?: string;
  min_price?: number;
  max_price?: number;
  min_support?: number;
  source_status?: string;
  search?: string;
  min_lat?: number;
  max_lat?: number;
  min_lon?: number;
  max_lon?: number;
  sort?: string;
  limit?: number;
  offset?: number;
};

export type MarkerPoint = {
  id: string;
  title: string;
  lat: number;
  lon: number;
  city?: string | null;
  country?: string | null;
  ask_price?: number | null;
  fair_value?: number | null;
  deal_score?: number | null;
  support?: number | null;
  value_delta_pct?: number | null;
  yield_pct?: number | null;
  source_status: string;
  watchlisted: boolean;
  memo_state: string;
  comp_review_state: string;
  valuation_status: string;
  valuation_reason?: string | null;
  valuation_ready: boolean;
  serving_eligible: boolean;
  serving_reason?: string | null;
  next_action: string;
  marker_color: string;
  marker_size: number;
  label: string;
  bedrooms?: number | null;
  surface_area_sqm?: number | null;
};

export type WorkbenchResponse = {
  filters: WorkbenchFilters;
  stats: {
    tracked: number;
    visible: number;
    watchlist_hits: number;
    support_median?: number | null;
    unavailable_count: number;
    available_count: number;
    valuation_ready_count: number;
    degraded_source_count: number;
  };
  markers: MarkerPoint[];
  table_rows: Array<Record<string, unknown>>;
  alerts: Array<Record<string, unknown>>;
  saved_searches: Array<Record<string, unknown>>;
  watchlists: Array<Record<string, unknown>>;
  jobs: Array<Record<string, unknown>>;
  source_summary: Record<string, number>;
};

export type ListingContextResponse = {
  listing: Record<string, unknown>;
  valuation: Record<string, unknown>;
  source_status: Record<string, unknown>;
  serving_eligible: boolean;
  serving_reason?: string | null;
  valuation_ready: boolean;
  can_run_valuation: boolean;
  watchlists: Array<Record<string, unknown>>;
  memos: Array<Record<string, unknown>>;
  comp_reviews: Array<Record<string, unknown>>;
  quality_events: Array<Record<string, unknown>>;
  next_action: string;
};

export type LayersResponse = {
  base_map: {
    provider: string;
    style: string;
  };
  defaults: string[];
  overlays: Array<{
    id: string;
    label: string;
    description: string;
    default: boolean;
    blocked: boolean;
    blocked_reason?: string;
  }>;
};

export type CollectionResponse<T> = {
  total: number;
  items: T[];
};
