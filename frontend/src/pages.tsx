import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { WorkbenchMap } from "./components/WorkbenchMap";
import { track } from "./track";
import type {
  CompCandidate,
  CompReviewWorkspaceResponse,
  DataGap,
  MarkerPoint,
  Memo,
  WorkbenchFilters,
  WorkbenchResponse,
  WorkbenchTableRow,
} from "./types";

function fmtMoney(value?: number | null) {
  if (value === undefined || value === null) return "N/A";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

function fmtPct(value?: number | null, digits = 1) {
  if (value === undefined || value === null) return "N/A";
  return `${(value * 100).toFixed(digits)}%`;
}

function fmtDateTime(value?: string | null) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatMaybeString(value?: string | null, fallback = "N/A") {
  return value && value.trim() ? value : fallback;
}

function formatMetricValue(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number") {
    if (Math.abs(value) <= 1) {
      return fmtPct(value);
    }
    return value.toLocaleString();
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

function formatValuationReason(value?: string | null) {
  const code = String(value ?? "").trim();
  if (!code) return "";
  const lookup: Record<string, string> = {
    target_city_required: "City is required before this listing can be valued.",
    target_surface_area_required: "Surface area is required before this listing can be valued.",
    target_coordinates_required: "Coordinates are required before this listing can be valued.",
    insufficient_comps: "Not enough comparable listings are available yet.",
    manual_valuation_required: "This listing is ready, but valuation has not been run yet.",
    blocked_source: "This listing is hidden because its source is blocked.",
    price_missing: "Listing price is missing.",
    price_out_of_range: "Listing price is outside the trusted serving range.",
    surface_area_out_of_range: "Surface area is outside the trusted serving range.",
    bedrooms_out_of_range: "Bedroom count is outside the trusted serving range.",
    bathrooms_out_of_range: "Bathroom count is outside the trusted serving range.",
    invalid_coordinates: "Listing coordinates are missing or invalid.",
    missing_required_fields: "Required listing fields are still missing.",
    images_missing: "The listing has no imagery yet.",
    description_missing: "The listing has no long description yet.",
    coordinates_missing: "Coordinates are missing, so map and comp quality are limited.",
  };
  return lookup[code] ?? code.replace(/_/g, " ");
}

function buildFilters(
  search: string,
  country: string,
  city: string,
  listingType: string,
  minPrice: string,
  maxPrice: string,
  minSupport: string,
  sourceStatus: string,
): WorkbenchFilters {
  return {
    search: search || undefined,
    country: country || undefined,
    city: city || undefined,
    listing_type: listingType || undefined,
    min_price: minPrice ? Number(minPrice) : undefined,
    max_price: maxPrice ? Number(maxPrice) : undefined,
    min_support: minSupport ? Number(minSupport) : undefined,
    source_status: sourceStatus || undefined,
    sort: "deal_score_desc",
    limit: 180,
  };
}

function statusClass(value?: string | null) {
  const slug = String(value ?? "neutral").toLowerCase().replace(/\s+/g, "-");
  return `status-pill status-${slug}`;
}

function sectionTitle(label: string, value: string, note?: string) {
  return (
    <div className="metric-card">
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      {note ? <p>{note}</p> : null}
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function DataGapCards({ gaps }: { gaps: DataGap[] }) {
  if (gaps.length === 0) return null;
  return (
    <div className="list-stack">
      {gaps.map((gap) => (
        <div key={gap.code} className={`warning-card warning-${gap.severity}`}>
          <strong>{gap.label}</strong>
          <p>{gap.detail || formatValuationReason(gap.code)}</p>
        </div>
      ))}
    </div>
  );
}

function OverviewStrip({ data }: { data: WorkbenchResponse }) {
  const nextItem = data.overview.review_queue[0];
  return (
    <div className="truth-grid">
      {sectionTitle("Actionable", String(data.overview.actionable_count), "Supported listings with usable confidence")}
      {sectionTitle("Degraded", String(data.overview.degraded_count), "Listings blocked by source trust or staleness")}
      {sectionTitle("Needs data", String(data.overview.needs_data_count), "Listings missing fields or comps")}
      {sectionTitle(
        "Next drill-down",
        nextItem ? nextItem.next_action : "No queue",
        nextItem ? `${nextItem.title} in ${formatMaybeString(nextItem.city, "unassigned area")}` : "No listing currently needs immediate review",
      )}
    </div>
  );
}

export function WorkbenchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [listingType, setListingType] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minSupport, setMinSupport] = useState("");
  const [sourceStatus, setSourceStatus] = useState("");
  const [onlyWatchlisted, setOnlyWatchlisted] = useState(false);
  const [onlyMemoReady, setOnlyMemoReady] = useState(false);
  const [onlyCompReady, setOnlyCompReady] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [selectedId, setSelectedId] = useState<string>();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [hovered, setHovered] = useState<MarkerPoint>();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [watchlistName, setWatchlistName] = useState("Decision hub basket");
  const [savedSearchName, setSavedSearchName] = useState("Truth-first lens");
  const [memoTitle, setMemoTitle] = useState("Listing memo draft");
  const trackedFiltersRef = useRef(false);

  const deferredSearch = useDeferredValue(search);
  const filters = useMemo(
    () =>
      buildFilters(
        deferredSearch,
        country,
        city,
        listingType,
        minPrice,
        maxPrice,
        minSupport,
        sourceStatus,
      ),
    [deferredSearch, country, city, listingType, minPrice, maxPrice, minSupport, sourceStatus],
  );

  const exploreQuery = useQuery({
    queryKey: ["workbench", filters],
    queryFn: () => api.explore(filters),
  });
  const layersQuery = useQuery({
    queryKey: ["layers"],
    queryFn: api.layers,
  });

  const visibleData = useMemo(() => {
    const base = exploreQuery.data;
    if (!base) return undefined;
    const markers = base.markers.filter((marker) => {
      if (onlyWatchlisted && !marker.watchlisted) return false;
      if (onlyMemoReady && marker.memo_state === "none") return false;
      if (onlyCompReady && marker.comp_review_state === "none") return false;
      return true;
    });
    const visibleIds = new Set(markers.map((marker) => marker.id));
    const tableRows = base.table_rows.filter((row) => visibleIds.has(row.id));
    return {
      ...base,
      markers,
      table_rows: tableRows,
      stats: {
        ...base.stats,
        visible: markers.length,
        watchlist_hits: markers.filter((marker) => marker.watchlisted).length,
        unavailable_count: markers.filter((marker) => marker.valuation_status !== "available").length,
        degraded_source_count: markers.filter((marker) => marker.source_status === "degraded").length,
      },
      overview: {
        ...base.overview,
        review_queue: base.overview.review_queue.filter((item) => visibleIds.has(item.listing_id)),
      },
    };
  }, [exploreQuery.data, onlyCompReady, onlyMemoReady, onlyWatchlisted]);

  const visibleSelectedIds = useMemo(() => {
    const visibleIds = new Set((visibleData?.markers ?? []).map((marker) => marker.id));
    return selectedIds.filter((id) => visibleIds.has(id));
  }, [selectedIds, visibleData?.markers]);

  useEffect(() => {
    if (!trackedFiltersRef.current) {
      trackedFiltersRef.current = true;
      return;
    }
    track({
      event_name: "workbench_filter_applied",
      route: "/workbench",
      subject_type: "lens",
      subject_id: "active",
      context: {
        has_search: Boolean(deferredSearch),
        has_country: Boolean(country),
        has_city: Boolean(city),
        has_listing_type: Boolean(listingType),
        has_source_state: Boolean(sourceStatus),
        advanced_open: advancedOpen,
      },
    });
  }, [advancedOpen, city, country, deferredSearch, listingType, sourceStatus]);

  const activeMarker = useMemo(() => {
    const markers = visibleData?.markers ?? [];
    const currentSelected = selectedId ? markers.find((marker) => marker.id === selectedId) : undefined;
    return currentSelected ?? hovered ?? markers[0];
  }, [hovered, selectedId, visibleData?.markers]);

  const contextQuery = useQuery({
    queryKey: ["listing-context", activeMarker?.id],
    queryFn: () => api.listingContext(activeMarker!.id),
    enabled: Boolean(activeMarker?.id),
  });

  const createWatchlist = useMutation({
    mutationFn: (listingIds: string[]) =>
      api.createWatchlist({
        name: `${watchlistName} ${new Date().toISOString().slice(11, 19)}`,
        description: "Created from the truth-first workbench",
        listing_ids: listingIds,
        filters: {
          ...filters,
          only_watchlisted: onlyWatchlisted,
          only_memo_ready: onlyMemoReady,
          only_comp_ready: onlyCompReady,
        },
      }),
    onSuccess: () => {
      track({
        event_name: "workbench_watchlist_created",
        route: "/workbench",
        subject_type: "watchlist",
        subject_id: watchlistName,
        context: { listing_count: selectedBasket.length },
      });
      void queryClient.invalidateQueries({ queryKey: ["workbench"] });
      void queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] });
      void queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });
  const createSavedSearch = useMutation({
    mutationFn: () =>
      api.createSavedSearch({
        name: `${savedSearchName} ${new Date().toISOString().slice(11, 19)}`,
        query: deferredSearch || null,
        filters: {
          ...filters,
          only_watchlisted: onlyWatchlisted,
          only_memo_ready: onlyMemoReady,
          only_comp_ready: onlyCompReady,
        },
        sort: { field: "deal_score", direction: "desc" },
      }),
    onSuccess: () => {
      track({
        event_name: "workbench_saved_lens",
        route: "/workbench",
        subject_type: "saved_search",
        subject_id: savedSearchName,
        context: { search: deferredSearch || null },
      });
      void queryClient.invalidateQueries({ queryKey: ["workbench"] });
      void queryClient.invalidateQueries({ queryKey: ["saved-searches"] });
    },
  });
  const createMemo = useMutation({
    mutationFn: (listingId: string) =>
      api.createMemo({
        title: `${memoTitle} ${new Date().toISOString().slice(11, 19)}`,
        listing_id: listingId,
        assumptions: ["Created from the workbench selection basket."],
        risks: ["Source health and data gaps should be reviewed before export."],
        sections: [
          {
            heading: "Recommendation framing",
            body: "Started from the truth-first workbench and should be finalized after dossier review.",
          },
        ],
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] });
      void queryClient.invalidateQueries({ queryKey: ["memos"] });
      track({
        event_name: "memo_published",
        route: "/workbench",
        subject_type: "listing",
        subject_id: activeMarker?.id ?? null,
        context: { source: "workbench" },
      });
    },
  });
  const createCompReview = useMutation({
    mutationFn: (listingId: string) =>
      api.createCompReview({
        listing_id: listingId,
        status: "draft",
        selected_comp_ids: [],
        rejected_comp_ids: [],
        overrides: {},
      }),
    onSuccess: (_, listingId) => {
      track({
        event_name: "comp_review_saved",
        route: `/comp-reviews/${listingId}`,
        subject_type: "listing",
        subject_id: listingId,
        context: { source: "workbench_start" },
      });
      navigate(`/comp-reviews/${listingId}`);
    },
  });
  const runValuation = useMutation({
    mutationFn: (listingId: string) => api.createValuation({ listing_id: listingId, persist: true }),
    onSuccess: async () => {
      track({
        event_name: "listing_valuation_run",
        route: `/listings/${activeMarker?.id ?? ""}`,
        subject_type: "listing",
        subject_id: activeMarker?.id ?? null,
        context: { source: "workbench" },
      });
      await queryClient.invalidateQueries({ queryKey: ["workbench"] });
      await queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] });
    },
  });

  const layerItems = layersQuery.data?.overlays ?? [];
  const loading = exploreQuery.isLoading || layersQuery.isLoading;
  const error = exploreQuery.error || layersQuery.error;
  const selectedBasket = visibleSelectedIds.length > 0 ? visibleSelectedIds : activeMarker ? [activeMarker.id] : [];
  const context = contextQuery.data;

  const handleSelect = (listingId: string, options: { multi: boolean }) => {
    setSelectedId(listingId);
    setSelectedIds((current) => {
      if (!options.multi) {
        return [listingId];
      }
      return current.includes(listingId)
        ? current.filter((id) => id !== listingId)
        : [...current, listingId];
    });
  };

  if (loading) {
    return <div className="page-card">Loading truth-first workbench…</div>;
  }

  if (error || !visibleData) {
    return (
      <div className="page-card error-state">
        {error instanceof Error ? error.message : "Workbench data failed to load."}
      </div>
    );
  }

  return (
    <div className="workbench-layout">
      <aside className="left-rail">
        <div className="brand-panel">
          <p className="eyebrow">Truth-first workbench</p>
          <h2>Lead with readiness, not more surface area</h2>
          <p>
            Keep the first decision simple: what is actionable now, what is degraded, and which listing deserves the next review.
          </p>
        </div>

        <div className="rail-section">
          <span className="eyebrow">Lens builder</span>
          <label>
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="City, listing, memo, source…"
            />
          </label>
          <label>
            Country
            <input value={country} onChange={(event) => setCountry(event.target.value.toUpperCase())} />
          </label>
          <label>
            City
            <input value={city} onChange={(event) => setCity(event.target.value)} placeholder="Madrid" />
          </label>
          <label>
            Listing type
            <select value={listingType} onChange={(event) => setListingType(event.target.value)}>
              <option value="">Any</option>
              <option value="sale">Sale</option>
              <option value="rent">Rent</option>
            </select>
          </label>
          <div className="metric-grid">
            <label>
              Min price
              <input value={minPrice} onChange={(event) => setMinPrice(event.target.value)} placeholder="120000" />
            </label>
            <label>
              Max price
              <input value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="900000" />
            </label>
          </div>
          <label>
            Support floor
            <input value={minSupport} onChange={(event) => setMinSupport(event.target.value)} placeholder="0.72" />
          </label>
          <label>
            Source state
            <select value={sourceStatus} onChange={(event) => setSourceStatus(event.target.value)}>
              <option value="">Any</option>
              <option value="supported">Supported</option>
              <option value="degraded">Degraded</option>
              <option value="experimental">Experimental</option>
              <option value="blocked">Blocked</option>
            </select>
          </label>
          <details className="disclosure-card" open={advancedOpen} onToggle={(event) => setAdvancedOpen((event.currentTarget as HTMLDetailsElement).open)}>
            <summary>Advanced filters and map options</summary>
            <div className="form-stack">
              <label><input type="checkbox" checked={onlyWatchlisted} onChange={() => setOnlyWatchlisted((value) => !value)} /> Only watchlisted</label>
              <label><input type="checkbox" checked={onlyMemoReady} onChange={() => setOnlyMemoReady((value) => !value)} /> Memo-linked only</label>
              <label><input type="checkbox" checked={onlyCompReady} onChange={() => setOnlyCompReady((value) => !value)} /> Comp-review only</label>
            </div>
            <div className="toggle-row">
              <label><input type="checkbox" checked={showHeat} onChange={() => setShowHeat((value) => !value)} /> Density heat</label>
              <label><input type="checkbox" checked={showLabels} onChange={() => setShowLabels((value) => !value)} /> Delta labels</label>
            </div>
            <div className="legend-list">
              {layerItems.map((layer) => (
                <div key={layer.id} className={`legend-item ${layer.blocked ? "is-blocked" : ""}`}>
                  <strong>{layer.label}</strong>
                  <p>{layer.description}</p>
                </div>
              ))}
            </div>
          </details>
        </div>
      </aside>

      <main className="center-stage">
        <div className="topbar-card">
          <div>
            <span className="eyebrow">Workbench</span>
            <h2>Overview first, decision next</h2>
            <p>
              Keep the map. Lose the noise. The screen should move you from readiness to shortlist to dossier without competing rails.
            </p>
          </div>
          <div className="topbar-actions">
            <div className="compact-field">
              <label>
                Lens name
                <input value={savedSearchName} onChange={(event) => setSavedSearchName(event.target.value)} />
              </label>
            </div>
            <button className="ghost-button" onClick={() => createSavedSearch.mutate()} disabled={createSavedSearch.isPending}>
              Save lens
            </button>
            <Link className="nav-chip" to="/watchlists">Decisions</Link>
            <Link className="nav-chip" to="/pipeline">Pipeline</Link>
          </div>
        </div>

        <OverviewStrip data={visibleData} />

        {visibleData.overview.actionable_count === 0 ? (
          <div className="warning-card">
            Nothing in the current lens is fully decision-ready. Use the review queue below to resolve
            degraded sources or missing valuation data instead of treating the list as a deal board.
          </div>
        ) : null}

        <div className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Shortlist</span>
              <h3>Next review candidates</h3>
            </div>
            <span className="chip">{visibleData.overview.review_queue.length} surfaced</span>
          </div>
          <div className="list-stack compact-list">
            {visibleData.overview.review_queue.length ? (
              visibleData.overview.review_queue.slice(0, 4).map((item) => (
                <button
                  key={item.listing_id}
                  className="list-card shortlist-row"
                  onClick={() => handleSelect(item.listing_id, { multi: false })}
                  type="button"
                >
                  <div className="panel-line">
                    <strong>{item.title}</strong>
                    <span className={statusClass(item.source_status)}>{item.source_status}</span>
                  </div>
                  <p>{item.next_action} · {formatMaybeString(item.city, "location pending")}</p>
                </button>
              ))
            ) : (
              <EmptyState
                title="No shortlisted reviews"
                body="The active lens has no visible listings after the current watchlist, memo, and comp-review filters."
              />
            )}
          </div>
        </div>

        <WorkbenchMap
          markers={visibleData.markers}
          selectedId={activeMarker?.id}
          selectedIds={visibleSelectedIds}
          showHeat={showHeat}
          showLabels={showLabels}
          onSelect={handleSelect}
          onHover={setHovered}
        />

        <div className="selection-dock">
          <div className="dock-header">
            <div>
              <h3>Selection basket</h3>
              <p>Pin rows from the map or table, then route them into watchlists, memos, or comp review.</p>
            </div>
            <div className="chip-row">
              <span className="chip">{visibleSelectedIds.length || 1} in basket</span>
              <span className="chip">{visibleData.stats.unavailable_count} unavailable</span>
              <span className="chip">{visibleData.stats.degraded_source_count} degraded</span>
            </div>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Listing</th>
                  <th>Ask</th>
                  <th>Fair value</th>
                  <th>Support</th>
                  <th>Source</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {visibleData.table_rows.map((row: WorkbenchTableRow) => (
                  <tr
                    key={row.id}
                    className={[
                      row.id === activeMarker?.id ? "is-selected" : "",
                      visibleSelectedIds.includes(row.id) ? "is-basketed" : "",
                    ].filter(Boolean).join(" ")}
                    onClick={(event) =>
                      handleSelect(row.id, {
                        multi: event.shiftKey || event.metaKey || event.ctrlKey,
                      })
                    }
                  >
                    <td>{row.title}</td>
                    <td>{fmtMoney(row.ask_price)}</td>
                    <td>{fmtMoney(row.fair_value)}</td>
                    <td>{fmtPct(row.support)}</td>
                    <td>{row.source_status}</td>
                    <td>{row.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <aside className="right-rail">
        <div className="rail-section">
          <span className="eyebrow">Active dossier rail</span>
          {activeMarker ? (
            <>
              <h3>{activeMarker.title}</h3>
              <p>
                {formatMaybeString(activeMarker.city, "City pending")}, {formatMaybeString(activeMarker.country, "Country pending")}
              </p>
              <div className="support-row">
                <span className={statusClass(activeMarker.source_status)}>{activeMarker.source_status}</span>
                <span className={statusClass(activeMarker.valuation_status)}>{activeMarker.valuation_status}</span>
              </div>
              <div className="metric-grid">
                {sectionTitle("Ask", fmtMoney(activeMarker.ask_price))}
                {sectionTitle("Fair value", fmtMoney(activeMarker.fair_value))}
                {sectionTitle("Support", fmtPct(activeMarker.support))}
                {sectionTitle("Value delta", fmtPct(activeMarker.value_delta_pct))}
              </div>
              {context ? (
                <>
                  <div className="list-card">
                    <strong>Trust</strong>
                    <p>{formatMaybeString(context.source_health.status)} · {context.source_health.reasons[0] || "No active source warning."}</p>
                  </div>
                  <DataGapCards gaps={context.data_gaps.slice(0, 2)} />
                </>
              ) : null}
              <div className="form-stack">
                <label>
                  Watchlist name
                  <input value={watchlistName} onChange={(event) => setWatchlistName(event.target.value)} />
                </label>
                <button
                  className="primary-button"
                  onClick={() => createWatchlist.mutate(selectedBasket)}
                  disabled={createWatchlist.isPending}
                >
                  Save basket to Decisions
                </button>
                <label>
                  Memo title
                  <input value={memoTitle} onChange={(event) => setMemoTitle(event.target.value)} />
                </label>
                <button className="primary-button" onClick={() => createMemo.mutate(activeMarker.id)} disabled={createMemo.isPending}>
                  Draft memo
                </button>
                {activeMarker.valuation_ready && activeMarker.valuation_status !== "available" ? (
                  <button
                    className="ghost-button"
                    onClick={() => runValuation.mutate(activeMarker.id)}
                    disabled={runValuation.isPending}
                  >
                    Run valuation
                  </button>
                ) : null}
                <button className="ghost-button" onClick={() => createCompReview.mutate(activeMarker.id)} disabled={createCompReview.isPending}>
                  Start comp review
                </button>
                <Link
                  className="ghost-button link-button"
                  to={`/listings/${activeMarker.id}`}
                  onClick={() =>
                    track({
                      event_name: "workbench_listing_opened",
                      route: "/workbench",
                      subject_type: "listing",
                      subject_id: activeMarker.id,
                      context: { source: "active_dossier_rail" },
                    })
                  }
                >
                  Open dossier
                </Link>
              </div>
            </>
          ) : (
            <p>Select a marker to open the dossier rail.</p>
          )}
        </div>
      </aside>
    </div>
  );
}

export function ListingPage() {
  const { listingId = "" } = useParams();
  const queryClient = useQueryClient();
  const contextQuery = useQuery({
    queryKey: ["listing-context", listingId],
    queryFn: () => api.listingContext(listingId),
  });
  const runValuation = useMutation({
    mutationFn: () => api.createValuation({ listing_id: listingId, persist: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["listing-context", listingId] });
      await queryClient.invalidateQueries({ queryKey: ["workbench"] });
    },
  });

  const context = contextQuery.data;
  if (contextQuery.isLoading) return <div className="page-card">Loading property dossier…</div>;
  if (!context) return <div className="page-card error-state">Listing context unavailable.</div>;

  const listing = context.listing;
  const location = listing.location;
  const compSignals = Object.entries(context.evidence_summary.signals).slice(0, 2);
  const confidenceBreakdown = Object.entries(context.evidence_summary.confidence_components).slice(0, 3);
  const marketSignals = Object.entries(context.market_context.signals).slice(0, 3);

  return (
    <div className="page-stack">
      <div className="page-card detail-hero">
        <div>
          <span className="eyebrow">Listing dossier</span>
          <h2>{listing.title}</h2>
          <p>
            {formatMaybeString(location?.city, "")} {formatMaybeString(location?.country, "")} · {formatMaybeString(listing.property_type)} · {formatMaybeString(context.source_health.status)}
          </p>
        </div>
        <div className="chip-row">
          <Link className="nav-chip" to={`/comp-reviews/${listingId}`}>Open comp workbench</Link>
          <Link className="nav-chip" to="/watchlists?tab=memos">Open Decisions</Link>
          {context.can_run_valuation ? (
            <button
              className="primary-button"
              onClick={() => {
                track({
                  event_name: "listing_valuation_run",
                  route: `/listings/${listingId}`,
                  subject_type: "listing",
                  subject_id: listingId,
                  context: { source: "dossier" },
                });
                runValuation.mutate();
              }}
              disabled={runValuation.isPending}
            >
              Run valuation now
            </button>
          ) : null}
        </div>
      </div>

      <div className="truth-grid">
        {sectionTitle("Ask", fmtMoney(listing.price))}
        {sectionTitle("Fair value", fmtMoney(context.valuation.fair_value))}
        {sectionTitle("Support", fmtPct(context.valuation.support))}
        {sectionTitle("Next action", context.next_action, context.valuation.reason ? formatValuationReason(context.valuation.reason) : undefined)}
      </div>

      <DataGapCards gaps={context.data_gaps} />

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Value moment</span>
              <h3>Decision summary</h3>
            </div>
            <span className={statusClass(context.source_health.status)}>{context.source_health.status}</span>
          </div>
          <div className="metric-grid">
            {sectionTitle("Value delta", fmtPct(context.valuation.value_delta_pct))}
            {sectionTitle("Projected 12m", fmtMoney(context.valuation.projected_value_12m))}
            {sectionTitle("Range low", fmtMoney(context.valuation.price_range_low))}
            {sectionTitle("Range high", fmtMoney(context.valuation.price_range_high))}
          </div>
          <p>
            {context.evidence_summary.thesis ||
              "No persisted valuation thesis exists yet. This dossier still shows source health, data gaps, and memo hooks so missing evidence is explicit."}
          </p>
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Trust</span>
              <h3>Health, freshness, and provenance</h3>
            </div>
            <span className={statusClass(context.source_health.latest_contract_status || context.source_health.status)}>
              {formatMaybeString(context.source_health.latest_contract_status, context.source_health.status)}
            </span>
          </div>
            <div className="list-stack">
              <div className="list-card">
                <strong>Reasons</strong>
                <p>{context.source_health.reasons.length ? context.source_health.reasons.join(", ") : "No active source warnings."}</p>
              </div>
            <div className="list-card">
              <strong>Last contract</strong>
              <p>{fmtDateTime(context.source_health.last_contract_at)}</p>
            </div>
              <div className="list-card">
                <strong>Last quality event</strong>
                <p>{fmtDateTime(context.source_health.last_quality_event_at)}</p>
              </div>
              <div className="timeline">
                {context.provenance_timeline.slice(0, 4).map((event) => (
                  <div key={event.id} className="timeline-item">
                    <strong>{event.title}</strong>
                    <p>{event.detail}</p>
                    <p>{fmtDateTime(event.at)}</p>
                  </div>
                ))}
              </div>
            </div>
        </section>
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Media ribbon</span>
              <h3>{context.media_summary.count} assets</h3>
            </div>
          </div>
          {context.media_summary.image_urls.length ? (
            <div className="media-grid">
              {context.media_summary.image_urls.slice(0, 6).map((imageUrl) => (
                <div key={imageUrl} className="media-card">
                  <img alt={listing.title} src={imageUrl} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No imagery yet"
              body="The dossier calls out missing listing images instead of leaving the media section blank."
            />
          )}
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Evidence ladder</span>
              <h3>Why the value view looks the way it does</h3>
            </div>
            <span className="chip">{context.evidence_summary.comp_count} comps</span>
          </div>
          <div className="list-stack">
            {context.evidence_summary.top_comps.length ? (
              context.evidence_summary.top_comps.map((comp) => (
                <div key={comp.id} className="list-card">
                  <strong>{comp.id}</strong>
                  <p>
                    {fmtMoney(comp.adj_price)} adjusted · similarity {fmtPct(comp.similarity_score)} · {comp.is_sold ? "sold anchor" : "active comp"}
                  </p>
                </div>
              ))
            ) : (
              <EmptyState
                title="No persisted comp ladder"
                body="This listing has no persisted valuation evidence yet, so the dossier stays explicit about the missing support."
              />
            )}
            {confidenceBreakdown.length ? (
              <div className="key-value-grid">
                {confidenceBreakdown.map(([key, value]) => (
                  <div key={key} className="list-card compact-card">
                    <strong>{key.replace(/_/g, " ")}</strong>
                    <p>{formatMetricValue(value)}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Market context</span>
              <h3>Only the signals that change the call</h3>
            </div>
          </div>
          <div className="key-value-grid">
            {marketSignals.length ? (
              marketSignals.map(([key, value]) => (
                <div key={key} className="list-card compact-card">
                  <strong>{key.replace(/_/g, " ")}</strong>
                  <p>{formatMetricValue(value)}</p>
                </div>
              ))
            ) : (
              <EmptyState
                title="No structured market signals"
                body="The listing still shows raw sentiment, tags, and activity timing, but no structured signal block has been persisted."
              />
            )}
            {compSignals.map(([key, value]) => (
              <div key={key} className="list-card compact-card">
                <strong>{key.replace(/_/g, " ")}</strong>
                <p>{formatMetricValue(value)}</p>
              </div>
            ))}
          </div>
          <div className="chip-row">
            {(context.market_context.tags || []).slice(0, 6).map((tag) => (
              <span key={tag} className="chip">{tag}</span>
            ))}
          </div>
          <details className="disclosure-card">
            <summary>Show all persisted market details</summary>
            <div className="key-value-grid">
              {Object.entries(context.market_context.analysis_meta).slice(0, 6).map(([key, value]) => (
                <div key={key} className="list-card compact-card">
                  <strong>{key.replace(/_/g, " ")}</strong>
                  <p>{formatMetricValue(value)}</p>
                </div>
              ))}
            </div>
          </details>
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Decision hooks</span>
              <h3>Memos, reviews, watchlists</h3>
            </div>
          </div>
          <div className="list-stack">
            <div className="list-card">
              <strong>{context.watchlists.length} watchlists</strong>
              <p>{context.watchlists.length ? context.watchlists.map((item) => item.name).join(", ") : "No watchlists yet."}</p>
            </div>
            <div className="list-card">
              <strong>{context.memos.length} memos</strong>
              <p>{context.memos.length ? context.memos.map((item) => item.title).join(", ") : "No memo drafts yet."}</p>
            </div>
            <div className="list-card">
              <strong>{context.comp_reviews.length} comp reviews</strong>
              <p>{context.comp_reviews.length ? context.comp_reviews.map((item) => item.status).join(", ") : "No comp review saved yet."}</p>
            </div>
          </div>
        </section>
      </div>

    </div>
  );
}

function toggleSelection(
  current: string[],
  candidateId: string,
  {
    mode,
    opposing,
  }: {
    mode: "select" | "reject" | "clear";
    opposing: string[];
  },
) {
  if (mode === "clear") {
    return current.filter((id) => id !== candidateId);
  }
  if (mode === "select" && current.includes(candidateId)) {
    return current.filter((id) => id !== candidateId);
  }
  if (mode === "reject" && current.includes(candidateId)) {
    return current.filter((id) => id !== candidateId);
  }
  return [...current.filter((id) => !opposing.includes(id)), candidateId];
}

function candidateActionLabel(candidate: CompCandidate, selectedIds: string[], rejectedIds: string[]) {
  if (selectedIds.includes(candidate.id)) return "Pinned";
  if (rejectedIds.includes(candidate.id)) return "Rejected";
  if (candidate.state === "suggested") return "Suggested";
  return "Candidate";
}

function buildCompReviewDraft(data: CompReviewWorkspaceResponse) {
  return {
    selectedIds: data.latest_review?.selected_comp_ids ?? data.pinned_comps.map((item) => item.id),
    rejectedIds: data.latest_review?.rejected_comp_ids ?? data.rejected_comps.map((item) => item.id),
    notes: data.latest_review?.notes ?? "",
    conditionAdjustment: String(data.latest_review?.overrides.condition_adjustment_pct ?? ""),
    locationAdjustment: String(data.latest_review?.overrides.location_adjustment_pct ?? ""),
    renovationAdjustment: String(data.latest_review?.overrides.renovation_adjustment_pct ?? ""),
  };
}

function CompReviewWorkspaceEditor({
  listingId,
  data,
}: {
  listingId: string;
  data: CompReviewWorkspaceResponse;
}) {
  const queryClient = useQueryClient();
  const initialDraft = buildCompReviewDraft(data);
  const [selectedIds, setSelectedIds] = useState<string[]>(initialDraft.selectedIds);
  const [rejectedIds, setRejectedIds] = useState<string[]>(initialDraft.rejectedIds);
  const [notes, setNotes] = useState(initialDraft.notes);
  const [conditionAdjustment, setConditionAdjustment] = useState(initialDraft.conditionAdjustment);
  const [locationAdjustment, setLocationAdjustment] = useState(initialDraft.locationAdjustment);
  const [renovationAdjustment, setRenovationAdjustment] = useState(initialDraft.renovationAdjustment);

  const saveReview = useMutation({
    mutationFn: () =>
      api.createCompReview({
        listing_id: listingId,
        status: "draft",
        selected_comp_ids: selectedIds,
        rejected_comp_ids: rejectedIds,
        overrides: {
          ...(conditionAdjustment ? { condition_adjustment_pct: Number(conditionAdjustment) } : {}),
          ...(locationAdjustment ? { location_adjustment_pct: Number(locationAdjustment) } : {}),
          ...(renovationAdjustment ? { renovation_adjustment_pct: Number(renovationAdjustment) } : {}),
        },
        notes,
      }),
    onSuccess: async () => {
      track({
        event_name: "comp_review_saved",
        route: `/comp-reviews/${listingId}`,
        subject_type: "listing",
        subject_id: listingId,
        context: { retained_count: selectedIds.length },
      });
      await queryClient.invalidateQueries({ queryKey: ["comp-review-workspace", listingId] });
      await queryClient.invalidateQueries({ queryKey: ["comp-reviews", listingId] });
      await queryClient.invalidateQueries({ queryKey: ["listing-context", listingId] });
    },
  });
  const publishMemo = useMutation({
    mutationFn: () =>
      api.createMemo({
        title: `Comp-reviewed memo ${new Date().toISOString().slice(0, 10)}`,
        listing_id: listingId,
        assumptions: ["Comp selection was curated in the comp workbench."],
        risks: ["Manual adjustments should be reviewed before committee circulation."],
        sections: [
          {
            heading: "Comp workbench summary",
            body: `Retained ${selectedIds.length || data.delta_preview.retained_count || 0} comps with analyst overrides recorded in the review log.`,
          },
        ],
      }),
    onSuccess: () => {
      track({
        event_name: "memo_published",
        route: `/comp-reviews/${listingId}`,
        subject_type: "listing",
        subject_id: listingId,
        context: { source: "comp_review" },
      });
      void queryClient.invalidateQueries({ queryKey: ["memos"] });
      void queryClient.invalidateQueries({ queryKey: ["listing-context", listingId] });
    },
  });

  return (
    <div className="page-stack">
      <div className="page-card detail-hero">
        <div>
          <span className="eyebrow">Comp workbench</span>
          <h2>{data.target.title}</h2>
          <p>
            Candidate pool, retained comps, adjustment matrix, and publish-to-memo path live in one
            analyst surface instead of three disconnected screens.
          </p>
        </div>
        <div className="chip-row">
          <span className="chip">{data.candidate_pool.length} candidates</span>
          <span className="chip">{selectedIds.length || data.delta_preview.retained_count} retained</span>
          <button
            className="primary-button"
            onClick={() => saveReview.mutate()}
            disabled={saveReview.isPending || !data.save_review.ready}
          >
            Save review
          </button>
          <button
            className="ghost-button"
            onClick={() => publishMemo.mutate()}
            disabled={publishMemo.isPending || !data.publish_to_memo.ready}
          >
            Publish to memo
          </button>
        </div>
        {!data.save_review.ready && data.save_review.reason ? (
          <p>{formatValuationReason(data.save_review.reason)}</p>
        ) : null}
      </div>

      <DataGapCards gaps={data.data_gaps} />

      <div className="truth-grid">
        {sectionTitle("Ask", fmtMoney(data.target.ask_price))}
        {sectionTitle("Baseline fair value", fmtMoney(data.baseline_valuation.fair_value))}
        {sectionTitle("Retained median", fmtMoney(data.delta_preview.retained_median))}
        {sectionTitle(
          "Shift vs baseline",
          fmtPct(data.delta_preview.baseline_shift_pct),
          data.publish_to_memo.ready
            ? "Ready for memo publication."
            : (data.publish_to_memo.reason ?? undefined),
        )}
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Candidate pool</span>
              <h3>Pin, reject, or leave under consideration</h3>
            </div>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Comp</th>
                  <th>Distance</th>
                  <th>Size delta</th>
                  <th>Implied value</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.candidate_pool.map((candidate) => (
                  <tr key={candidate.id}>
                    <td>{candidate.title}</td>
                    <td>{candidate.distance_km.toFixed(1)} km</td>
                    <td>{fmtPct(candidate.size_delta_pct)}</td>
                    <td>{fmtMoney(candidate.implied_value)}</td>
                    <td>{candidateActionLabel(candidate, selectedIds, rejectedIds)}</td>
                    <td>
                      <div className="chip-row">
                        <button
                          className="ghost-button compact-button"
                          onClick={() =>
                            setSelectedIds((current) =>
                              toggleSelection(current, candidate.id, { mode: "select", opposing: rejectedIds }),
                            )
                          }
                        >
                          {selectedIds.includes(candidate.id) ? "Unpin" : "Pin"}
                        </button>
                        <button
                          className="ghost-button compact-button"
                          onClick={() =>
                            setRejectedIds((current) =>
                              toggleSelection(current, candidate.id, { mode: "reject", opposing: selectedIds }),
                            )
                          }
                        >
                          {rejectedIds.includes(candidate.id) ? "Undo reject" : "Reject"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Adjustment matrix</span>
              <h3>Analyst overrides</h3>
            </div>
          </div>
          <div className="list-stack">
            <label>
              Condition adjustment %
              <input value={conditionAdjustment} onChange={(event) => setConditionAdjustment(event.target.value)} placeholder="0.02" />
            </label>
            <label>
              Location adjustment %
              <input value={locationAdjustment} onChange={(event) => setLocationAdjustment(event.target.value)} placeholder="0.01" />
            </label>
            <label>
              Renovation adjustment %
              <input value={renovationAdjustment} onChange={(event) => setRenovationAdjustment(event.target.value)} placeholder="0.03" />
            </label>
            <label>
              Override note
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} />
            </label>
          </div>
          <div className="key-value-grid">
            {data.adjustment_cards.length ? (
              data.adjustment_cards.map((card) => (
                <div key={card.id} className="list-card compact-card">
                  <strong>{card.label}</strong>
                  <p>{formatMetricValue(card.value)}</p>
                </div>
              ))
            ) : (
              <EmptyState
                title="No saved adjustments"
                body="The workbench still shows the matrix explicitly so analysts can see that no overrides have been applied yet."
              />
            )}
          </div>
        </section>
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Memo gate</span>
              <h3>Keep the decision simple</h3>
            </div>
          </div>
          <div className="metric-grid">
            {sectionTitle("Candidate pool median", fmtMoney(data.delta_preview.candidate_pool_median))}
            {sectionTitle("Retained median", fmtMoney(data.delta_preview.retained_median))}
            {sectionTitle("Pinned delta", fmtPct(data.delta_preview.pinned_delta_pct))}
            {sectionTitle("Retained count", String(data.delta_preview.retained_count))}
          </div>
            <div className="list-card">
              <strong>Memo readiness</strong>
              <p>{data.publish_to_memo.ready ? "Ready to publish with current retained set." : data.publish_to_memo.reason}</p>
            </div>
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Override log</span>
              <h3>Audit trail</h3>
            </div>
          </div>
          <details className="disclosure-card">
            <summary>Show review history and guardrails</summary>
            <div className="timeline">
              {data.override_log.length ? (
                data.override_log.map((item) => (
                  <div key={item.id} className="timeline-item">
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                    <p>{fmtDateTime(item.at)}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No saved review history" body="Save the current comp selection to persist the audit trail." />
              )}
              {data.guardrails.map((rule) => (
                <div key={rule} className="timeline-item">
                  <strong>Guardrail</strong>
                  <p>{rule}</p>
                </div>
              ))}
            </div>
          </details>
        </section>
      </div>
    </div>
  );
}

export function CompReviewPage() {
  const { listingId = "" } = useParams();
  const workspaceQuery = useQuery({
    queryKey: ["comp-review-workspace", listingId],
    queryFn: () => api.compReviewWorkspace(listingId),
  });

  if (workspaceQuery.isLoading) return <div className="page-card">Loading comp workbench…</div>;
  if (!workspaceQuery.data) return <div className="page-card error-state">Comp workbench unavailable.</div>;

  const reviewKey = [
    listingId,
    workspaceQuery.data.latest_review?.id ?? "new",
    workspaceQuery.data.latest_review?.updated_at ?? "unset",
  ].join(":");

  return <CompReviewWorkspaceEditor key={reviewKey} listingId={listingId} data={workspaceQuery.data} />;
}

type DecisionTab = "watchlists" | "saved-searches" | "memos";

function tabButton(active: boolean) {
  return `global-nav-link${active ? " is-active" : ""}`;
}

function MemoExport({ memo }: { memo: Memo }) {
  const exportMutation = useMutation({
    mutationFn: () => api.exportMemo(memo.id),
  });

  return (
    <div className="list-card">
      <div className="panel-line">
        <strong>{memo.title}</strong>
        <span className={statusClass(memo.status)}>{memo.status}</span>
      </div>
      <p>{memo.sections[0]?.body || "No memo body yet."}</p>
      <button className="ghost-button compact-button" onClick={() => exportMutation.mutate()}>
        Export memo
      </button>
      {exportMutation.data ? <pre className="export-card">{exportMutation.data.content}</pre> : null}
    </div>
  );
}

export function DecisionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const activeTab: DecisionTab =
    requestedTab === "memos"
      ? "memos"
      : requestedTab === "saved-searches"
        ? "saved-searches"
        : "watchlists";
  const watchlistsQuery = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists });
  const savedSearchesQuery = useQuery({ queryKey: ["saved-searches"], queryFn: api.savedSearches });
  const memosQuery = useQuery({ queryKey: ["memos"], queryFn: api.memos });

  return (
    <div className="page-stack">
      <div className="page-card detail-hero">
        <div>
          <span className="eyebrow">Decision hub</span>
          <h2>Watchlists and memos stay together as one decision surface</h2>
          <p>
            This replaces the split watchlist and memo navigation so the product has one calm
            destination for saved conviction and published output.
          </p>
        </div>
        <div className="chip-row">
          <span className="chip">{watchlistsQuery.data?.total ?? 0} watchlists</span>
          <span className="chip">{savedSearchesQuery.data?.total ?? 0} saved searches</span>
          <span className="chip">{memosQuery.data?.total ?? 0} memos</span>
          <Link className="nav-chip" to="/workbench">Back to Workbench</Link>
        </div>
      </div>

      <div className="global-nav decision-tabs">
        <button className={tabButton(activeTab === "watchlists")} onClick={() => setSearchParams({ tab: "watchlists" })}>Watchlists</button>
        <button className={tabButton(activeTab === "saved-searches")} onClick={() => setSearchParams({ tab: "saved-searches" })}>Saved searches</button>
        <button className={tabButton(activeTab === "memos")} onClick={() => setSearchParams({ tab: "memos" })}>Memos</button>
      </div>

      {activeTab === "watchlists" ? (
        <div className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Watchlist board</span>
              <h3>Grouped by analyst intent</h3>
            </div>
          </div>
          <div className="queue-grid">
            {(watchlistsQuery.data?.items ?? []).length ? (
              watchlistsQuery.data!.items.map((watchlist) => (
                <div key={watchlist.id} className="list-card">
                  <strong>{watchlist.name}</strong>
                  <p>{formatMaybeString(watchlist.description, "No watchlist description yet.")}</p>
                  <div className="chip-row">
                    <span className="chip">{watchlist.listing_ids.length} listings</span>
                    <span className={statusClass(watchlist.status)}>{watchlist.status}</span>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState title="No watchlists yet" body="Save a basket from the workbench to start tracking decisions here." />
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "saved-searches" ? (
        <div className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Reusable lens library</span>
              <h3>Saved search presets from the workbench</h3>
            </div>
          </div>
          <div className="queue-grid">
            {(savedSearchesQuery.data?.items ?? []).length ? (
              savedSearchesQuery.data!.items.map((savedSearch) => (
                <div key={savedSearch.id} className="list-card">
                  <strong>{savedSearch.name}</strong>
                  <p>{formatMaybeString(savedSearch.query, "No free-text query saved.")}</p>
                  <div className="chip-row">
                    <span className="chip">{Object.keys(savedSearch.filters ?? {}).length} filters</span>
                    <span className="chip">
                      {formatMaybeString(String(savedSearch.sort?.field ?? ""), "No sort field")}
                    </span>
                  </div>
                  <p>{formatMaybeString(savedSearch.notes, "Saved from the workbench filter state.")}</p>
                </div>
              ))
            ) : (
              <EmptyState title="No saved searches yet" body="Save a lens from the workbench to reuse the exact search state here." />
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "memos" ? (
        <div className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Memo queue</span>
              <h3>Decision output and export</h3>
            </div>
          </div>
          <div className="list-stack">
            {(memosQuery.data?.items ?? []).length ? (
              memosQuery.data!.items.map((memo) => <MemoExport key={memo.id} memo={memo} />)
            ) : (
              <EmptyState title="No memo drafts yet" body="Draft a memo from the workbench or comp review to populate this queue." />
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function PipelinePage() {
  const trustSummaryQuery = useQuery({ queryKey: ["pipeline-trust-summary"], queryFn: api.pipelineTrustSummary });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  const coverageQuery = useQuery({ queryKey: ["coverage"], queryFn: api.coverage });
  const qualityQuery = useQuery({ queryKey: ["quality"], queryFn: api.quality });
  const benchmarkQuery = useQuery({ queryKey: ["benchmarks"], queryFn: api.benchmarks });
  const contractQuery = useQuery({ queryKey: ["source-contract-runs"], queryFn: api.sourceContracts });

  const trustSummary = trustSummaryQuery.data;
  const sourceSummary = trustSummary?.source_summary.counts ?? {};
  const latestBenchmark = trustSummary?.benchmark_gate;

  const openBlocker = (title: string) => {
    track({
      event_name: "pipeline_blocker_opened",
      route: "/pipeline",
      subject_type: "blocker",
      subject_id: title,
      context: { source: "trust_summary" },
    });
  };

  return (
    <div className="page-stack">
      <div className="page-card detail-hero">
        <div>
          <span className="eyebrow">Pipeline trust surface</span>
          <h2>Trust first. Operations second.</h2>
          <p>
            Analysts should be able to answer one question quickly: is the product trustworthy enough to act on right now?
          </p>
        </div>
      </div>

      <div className="truth-grid">
        {sectionTitle("Freshness", trustSummary?.freshness.needs_refresh ? "Needs refresh" : "Fresh")}
        {sectionTitle("Supported", String(sourceSummary.supported ?? 0))}
        {sectionTitle("Blocked", String(sourceSummary.blocked ?? 0))}
        {sectionTitle("Benchmark gate", latestBenchmark ? formatMaybeString(latestBenchmark.status) : "No runs")}
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Top blockers</span>
              <h3>Why analysts should pause or proceed</h3>
            </div>
          </div>
          <div className="list-stack">
            {(trustSummary?.top_blockers ?? []).length ? (
              trustSummary!.top_blockers.map((blocker) => (
                <button key={`${blocker.kind}-${blocker.title}`} className="list-card shortlist-row" onClick={() => openBlocker(blocker.title)} type="button">
                  <div className="panel-line">
                    <strong>{blocker.title}</strong>
                    <span className={statusClass(blocker.kind)}>{blocker.kind}</span>
                  </div>
                  <p>{blocker.detail}</p>
                </button>
              ))
            ) : (
              <EmptyState title="No active blockers" body="The trust surface stays explicit when the latest known state does not show active analyst-facing blockers." />
            )}
          </div>
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Source summary</span>
              <h3>Where confidence is strongest and weakest</h3>
            </div>
          </div>
          <div className="list-stack">
            {(trustSummary?.source_summary.top_sources ?? []).length ? (
              trustSummary!.source_summary.top_sources.map((source) => (
                <div key={source.source_id} className="list-card">
                  <div className="panel-line">
                    <strong>{source.name}</strong>
                    <span className={statusClass(source.status)}>{source.status}</span>
                  </div>
                  <p>{source.reasons.length ? source.reasons.join(", ") : "No active source warnings."}</p>
                </div>
              ))
            ) : (
              <EmptyState
                title="No source audit data"
                body="The trust surface keeps missing source-capability audits explicit instead of showing an empty panel."
              />
            )}
          </div>
        </section>
      </div>

      <div className="detail-main-grid">
        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Benchmark gate</span>
              <h3>Latest run</h3>
            </div>
          </div>
          {benchmarkQuery.data?.items[0] ? (
            <div className="list-stack">
              <div className="list-card">
                <strong>{benchmarkQuery.data!.items[0].status}</strong>
                <p>{fmtDateTime(benchmarkQuery.data!.items[0].completed_at || benchmarkQuery.data!.items[0].created_at)}</p>
              </div>
              <div className="key-value-grid">
                {Object.entries(benchmarkQuery.data!.items[0].metrics).slice(0, 4).map(([key, value]) => (
                  <div key={key} className="list-card compact-card">
                    <strong>{key.replace(/_/g, " ")}</strong>
                    <p>{formatMetricValue(value)}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              title="No benchmark runs"
              body="The screen keeps the benchmark gate explicit even when the underlying data has not been generated yet."
            />
          )}
        </section>

        <section className="page-card">
          <div className="panel-line">
            <div>
              <span className="eyebrow">Recent quality signals</span>
              <h3>Most recent incidents</h3>
            </div>
          </div>
          <div className="timeline">
            {(trustSummary?.latest_quality_events ?? []).length ? (
              trustSummary!.latest_quality_events.map((item) => (
                <div key={item.id} className="timeline-item">
                  <strong>{item.code}</strong>
                  <p>{formatMaybeString(item.source_id, "unknown source")} · {item.severity}</p>
                  <p>{fmtDateTime(item.created_at)}</p>
                </div>
              ))
            ) : (
              <EmptyState title="No quality events" body="The trust surface keeps a clean no-incident state explicit rather than leaving the stream blank." />
            )}
          </div>
        </section>
      </div>

      <details className="page-card disclosure-card">
        <summary>Show operational details</summary>
        <div className="detail-main-grid">
          <section className="page-card inset-card">
            <div className="panel-line">
              <div>
                <span className="eyebrow">Jobs</span>
                <h3>Recent execution</h3>
              </div>
            </div>
            <div className="list-stack">
              {(jobsQuery.data?.items ?? []).length ? (
                jobsQuery.data!.items.slice(0, 6).map((job) => (
                  <div key={job.id} className="list-card">
                    <div className="panel-line">
                      <strong>{job.job_type}</strong>
                      <span className={statusClass(job.status)}>{job.status}</span>
                    </div>
                    <p>{fmtDateTime(job.created_at)}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No job history" body="The pipeline screen keeps empty operational history explicit instead of rendering blank space." />
              )}
            </div>
          </section>

          <section className="page-card inset-card">
            <div className="panel-line">
              <div>
                <span className="eyebrow">Coverage</span>
                <h3>Segment detail</h3>
              </div>
            </div>
            <div className="list-stack">
              {(coverageQuery.data?.items ?? []).length ? (
                coverageQuery.data!.items.slice(0, 6).map((item) => (
                  <div key={item.id} className="list-card">
                    <strong>{item.segment_key} · {item.segment_value}</strong>
                    <p>{item.status} · coverage {fmtPct(item.empirical_coverage)} · sample {item.sample_size}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No coverage report" body="Coverage gaps are first-class states, not silent omissions." />
              )}
            </div>
          </section>
        </div>
        <div className="detail-main-grid">
          <section className="page-card inset-card">
            <div className="panel-line">
              <div>
                <span className="eyebrow">Quality stream</span>
                <h3>Expanded incident list</h3>
              </div>
            </div>
            <div className="timeline">
              {(qualityQuery.data?.items ?? []).length ? (
                qualityQuery.data!.items.slice(0, 10).map((item) => (
                  <div key={item.id} className="timeline-item">
                    <strong>{item.code}</strong>
                    <p>{formatMaybeString(item.source_id, "unknown source")} · {item.severity}</p>
                    <p>{fmtDateTime(item.created_at)}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No quality events" body="The pipeline keeps a clean no-incident state explicit rather than leaving the stream blank." />
              )}
            </div>
          </section>

          <section className="page-card inset-card">
            <div className="panel-line">
              <div>
                <span className="eyebrow">Contract history</span>
                <h3>Latest checks</h3>
              </div>
            </div>
            <div className="timeline">
              {(contractQuery.data?.items ?? []).length ? (
                contractQuery.data!.items.slice(0, 8).map((item) => (
                  <div key={item.id} className="timeline-item">
                    <strong>{item.source_id}</strong>
                    <p>{item.status}</p>
                    <p>{fmtDateTime(item.created_at)}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No contract history" body="If contract-backed checks have not run yet, the product says so explicitly." />
              )}
            </div>
          </section>
        </div>
      </details>
    </div>
  );
}
