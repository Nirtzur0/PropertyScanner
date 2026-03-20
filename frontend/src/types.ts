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

export type ListingLocation = {
  lat?: number | null;
  lon?: number | null;
  address_full?: string | null;
  city?: string | null;
  zip_code?: string | null;
  country?: string | null;
};

export type ListingRecord = {
  id: string;
  source_id: string;
  external_id: string;
  url: string;
  title: string;
  description?: string | null;
  price?: number | null;
  currency?: string | null;
  listing_type?: string | null;
  estimated_rent?: number | null;
  gross_yield?: number | null;
  sold_price?: number | null;
  property_type?: string | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  surface_area_sqm?: number | null;
  plot_area_sqm?: number | null;
  floor?: number | null;
  has_elevator?: boolean | null;
  location?: ListingLocation | null;
  image_urls?: string[];
  vlm_description?: string | null;
  text_sentiment?: number | null;
  image_sentiment?: number | null;
  analysis_meta?: Record<string, string | number | boolean | null>;
  listed_at?: string | null;
  updated_at?: string | null;
  status?: string | null;
  sold_at?: string | null;
  tags?: string[];
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

export type WorkbenchTableRow = {
  id: string;
  title: string;
  city?: string | null;
  country?: string | null;
  ask_price?: number | null;
  fair_value?: number | null;
  deal_score?: number | null;
  support?: number | null;
  source_status: string;
  valuation_status: string;
  valuation_ready: boolean;
  serving_eligible: boolean;
  serving_reason?: string | null;
  watchlisted: boolean;
  memo_state: string;
  comp_review_state: string;
  next_action: string;
};

export type WorkbenchQueueItem = {
  listing_id: string;
  title: string;
  city?: string | null;
  next_action: string;
  source_status: string;
  valuation_status: string;
  support?: number | null;
  ask_price?: number | null;
  fair_value?: number | null;
};

export type WorkbenchOverview = {
  actionable_count: number;
  degraded_count: number;
  needs_data_count: number;
  review_queue: WorkbenchQueueItem[];
};

export type WorkbenchStats = {
  tracked: number;
  visible: number;
  watchlist_hits: number;
  support_median?: number | null;
  unavailable_count: number;
  available_count: number;
  valuation_ready_count: number;
  degraded_source_count: number;
};

export type ValuationSummary = {
  valuation_status: string;
  fair_value?: number | null;
  deal_score?: number | null;
  support?: number | null;
  value_delta_pct?: number | null;
  yield_pct?: number | null;
  price_range_low?: number | null;
  price_range_high?: number | null;
  uncertainty_pct?: number | null;
  reason?: string | null;
  projected_value_12m?: number | null;
  valuation_ready: boolean;
};

export type DataGap = {
  code: string;
  label: string;
  severity: string;
  detail?: string | null;
};

export type DataQualityEvent = {
  id: string;
  source_id?: string | null;
  listing_id?: string | null;
  field_name?: string | null;
  severity: string;
  code: string;
  details: Record<string, string | number | boolean | null>;
  created_at?: string | null;
};

export type SourceHealth = {
  status: string;
  reasons: string[];
  metrics: Record<string, string | number | boolean | null>;
  last_contract_at?: string | null;
  last_quality_event_at?: string | null;
  latest_contract_status?: string | null;
};

export type EvidenceComp = {
  id: string;
  url?: string | null;
  observed_month?: string | null;
  raw_price?: number | null;
  adj_factor?: number | null;
  adj_price?: number | null;
  attention_weight?: number | null;
  is_sold?: boolean | null;
  similarity_score?: number | null;
};

export type EvidenceSummary = {
  available: boolean;
  thesis?: string | null;
  model_used?: string | null;
  calibration_status?: string | null;
  comp_count: number;
  sold_comp_count: number;
  confidence_components: Record<string, string | number | boolean | null>;
  signals: Record<string, string | number | boolean | null>;
  top_comps: EvidenceComp[];
};

export type MarketContext = {
  city?: string | null;
  country?: string | null;
  text_sentiment?: number | null;
  image_sentiment?: number | null;
  tags: string[];
  signals: Record<string, string | number | boolean | null>;
  analysis_meta: Record<string, string | number | boolean | null>;
  listed_at?: string | null;
  updated_at?: string | null;
};

export type MediaSummary = {
  count: number;
  primary_image_url?: string | null;
  image_urls: string[];
  has_gallery: boolean;
};

export type TimelineEvent = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  status?: string | null;
  at?: string | null;
};

export type Watchlist = {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  listing_ids: string[];
  filters: Record<string, string | number | boolean | null>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SavedSearch = {
  id: string;
  name: string;
  query?: string | null;
  filters: Record<string, string | number | boolean | null>;
  sort: Record<string, string | number | boolean | null>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type MemoSection = {
  heading: string;
  body: string;
};

export type Memo = {
  id: string;
  title: string;
  listing_id?: string | null;
  watchlist_id?: string | null;
  status: string;
  assumptions: string[];
  risks: string[];
  sections: MemoSection[];
  export_format: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CompReview = {
  id: string;
  listing_id: string;
  status: string;
  selected_comp_ids: string[];
  rejected_comp_ids: string[];
  overrides: Record<string, string | number | boolean | null>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type JobRun = {
  id: string;
  job_type: string;
  status: string;
  payload?: Record<string, string | number | boolean | null>;
  result?: Record<string, string | number | boolean | null>;
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type AgentRun = {
  id: string;
  created_at?: string | null;
  query: string;
  target_areas: string[];
  strategy?: string | null;
  plan: Record<string, string | number | boolean | null>;
  status: string;
  summary?: string | null;
  error?: string | null;
  listings_count: number;
  evaluations_count: number;
  top_listing_ids: string[];
  ui_blocks: Array<Record<string, string | number | boolean | null>>;
};

export type SourceCapabilityAudit = {
  source_id: string;
  name: string;
  enabled: boolean;
  countries: string[];
  status: string;
  reasons: string[];
  metrics: Record<string, string | number | boolean | null>;
};

export type SourceAuditResponse = {
  generated_at?: string | null;
  summary: Record<string, number>;
  sources: SourceCapabilityAudit[];
};

export type SourceContractRun = {
  id: string;
  source_id: string;
  status: string;
  metrics: Record<string, string | number | boolean | null>;
  created_at?: string | null;
};

export type CoverageReport = {
  id: string;
  listing_type: string;
  segment_key: string;
  segment_value: string;
  sample_size: number;
  empirical_coverage?: number | null;
  avg_interval_width?: number | null;
  status: string;
  report: Record<string, string | number | boolean | null>;
  created_at?: string | null;
};

export type BenchmarkRun = {
  id: string;
  status: string;
  config: Record<string, string | number | boolean | null>;
  metrics: Record<string, string | number | boolean | null>;
  output_json_path?: string | null;
  output_md_path?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
};

export type UIEventPayload = {
  event_name: string;
  route: string;
  subject_type?: string | null;
  subject_id?: string | null;
  context?: Record<string, string | number | boolean | null | undefined>;
  occurred_at: string;
};

export type PipelineTrustBlocker = {
  kind: string;
  title: string;
  detail: string;
};

export type PipelineTrustSummaryResponse = {
  freshness: {
    needs_refresh: boolean;
    status: string;
    reasons: string[];
  };
  source_summary: {
    counts: Record<string, number>;
    top_sources: Array<{
      source_id?: string | null;
      name?: string | null;
      status?: string | null;
      reasons: string[];
    }>;
  };
  top_blockers: PipelineTrustBlocker[];
  benchmark_gate: {
    status: string;
    created_at?: string | null;
    completed_at?: string | null;
  };
  jobs_summary: {
    running: number;
    failed: number;
    recent: Array<{
      id: string;
      job_type: string;
      status: string;
      created_at?: string | null;
    }>;
  };
  latest_quality_events: DataQualityEvent[];
  details_available: {
    jobs: boolean;
    coverage: boolean;
    quality: boolean;
    source_contracts: boolean;
  };
};

export type AssumptionBadge = {
  id: string;
  label: string;
  status: string;
  artifact_ids: string[];
  summary: string;
  guide_path?: string | null;
};

export type PipelineStatusResponse = {
  status?: string;
  db_path?: string;
  listings_count?: number;
  listings_last_seen?: string | null;
  needs_refresh?: boolean;
  reasons?: string[];
  source_support?: {
    doc_path?: string | null;
    summary: Record<string, number>;
    sources: Array<Record<string, string | number | boolean | null>>;
  };
  source_capabilities?: SourceAuditResponse;
  model_readiness?: {
    ready?: boolean;
    reasons?: string[];
    sale_rows?: number;
    closed_label_rows?: number;
  };
  assumption_badges?: AssumptionBadge[];
};

export type ListingContextResponse = {
  listing: ListingRecord;
  valuation: ValuationSummary;
  source_status: SourceCapabilityAudit;
  source_health: SourceHealth;
  serving_eligible: boolean;
  serving_reason?: string | null;
  valuation_ready: boolean;
  can_run_valuation: boolean;
  watchlists: Watchlist[];
  memos: Memo[];
  comp_reviews: CompReview[];
  quality_events: DataQualityEvent[];
  media_summary: MediaSummary;
  evidence_summary: EvidenceSummary;
  market_context: MarketContext;
  provenance_timeline: TimelineEvent[];
  data_gaps: DataGap[];
  next_action: string;
};

export type CompCandidate = {
  id: string;
  title: string;
  city?: string | null;
  country?: string | null;
  ask_price?: number | null;
  surface_area_sqm?: number | null;
  bedrooms?: number | null;
  similarity: number;
  distance_km: number;
  size_delta_pct?: number | null;
  implied_value?: number | null;
  state: string;
  selected: boolean;
  rejected: boolean;
};

export type AdjustmentCard = {
  id: string;
  label: string;
  value: string | number | boolean | null;
  kind: string;
};

export type DeltaPreview = {
  candidate_pool_median?: number | null;
  retained_median?: number | null;
  baseline_fair_value?: number | null;
  pinned_delta_pct?: number | null;
  baseline_shift_pct?: number | null;
  retained_count: number;
};

export type CompReviewWorkspaceResponse = {
  target: {
    id: string;
    title: string;
    city?: string | null;
    country?: string | null;
    ask_price?: number | null;
    property_type?: string | null;
    listing_type?: string | null;
    bedrooms?: number | null;
    bathrooms?: number | null;
    surface_area_sqm?: number | null;
  };
  baseline_valuation: ValuationSummary;
  latest_review?: CompReview | null;
  candidate_pool: CompCandidate[];
  pinned_comps: CompCandidate[];
  rejected_comps: CompCandidate[];
  adjustment_cards: AdjustmentCard[];
  delta_preview: DeltaPreview;
  override_log: Array<{
    id: string;
    title: string;
    detail: string;
    at?: string | null;
  }>;
  publish_to_memo: {
    ready: boolean;
    reason?: string | null;
    existing_memo_count: number;
  };
  save_review: {
    ready: boolean;
    reason?: string | null;
  };
  guardrails: string[];
  data_gaps: DataGap[];
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

export type WorkbenchResponse = {
  filters: WorkbenchFilters;
  stats: WorkbenchStats;
  overview: WorkbenchOverview;
  markers: MarkerPoint[];
  table_rows: WorkbenchTableRow[];
  alerts: DataQualityEvent[];
  saved_searches: SavedSearch[];
  watchlists: Watchlist[];
  jobs: JobRun[];
  source_summary: Record<string, number>;
};

export type CollectionResponse<T> = {
  total: number;
  items: T[];
};
