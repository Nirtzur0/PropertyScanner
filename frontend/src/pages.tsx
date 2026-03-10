import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import { api } from "./api";
import { WorkbenchMap } from "./components/WorkbenchMap";
import type { ListingContextResponse, MarkerPoint, WorkbenchFilters } from "./types";

function fmtMoney(value?: number | null) {
  if (value === undefined || value === null) return "N/A";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

function fmtPct(value?: number | null) {
  if (value === undefined || value === null) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMaybeString(value: unknown, fallback = "N/A") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function formatValuationReason(value: unknown) {
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
  };
  return lookup[code] ?? code.replace(/_/g, " ");
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

function getStatusClass(value: unknown) {
  const slug = String(value ?? "neutral").toLowerCase().replace(/\s+/g, "-");
  return `status-pill status-${slug}`;
}

function median(values: number[]) {
  if (values.length === 0) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

type TableRow = Record<string, unknown>;

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
  const [watchlistName, setWatchlistName] = useState("Workbench picks");
  const [savedSearchName, setSavedSearchName] = useState("Map lens");
  const [memoTitle, setMemoTitle] = useState("Map workbench memo");

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
    const tableRows = base.table_rows.filter((row) => visibleIds.has(String(row.id)));
    const supportMedian = median(
      markers
        .map((marker) => marker.support)
        .filter((value): value is number => value !== null && value !== undefined),
    );
    return {
      ...base,
      markers,
      table_rows: tableRows,
      stats: {
        ...base.stats,
        visible: markers.length,
        watchlist_hits: markers.filter((marker) => marker.watchlisted).length,
        support_median: supportMedian,
        unavailable_count: markers.filter((marker) => marker.valuation_status !== "available").length,
        degraded_source_count: markers.filter((marker) => marker.source_status === "degraded").length,
      },
    };
  }, [exploreQuery.data, onlyCompReady, onlyMemoReady, onlyWatchlisted]);

  useEffect(() => {
    const visibleIds = new Set((visibleData?.markers ?? []).map((marker) => marker.id));
    setSelectedIds((current) => current.filter((id) => visibleIds.has(id)));
    setSelectedId((current) => (current && visibleIds.has(current) ? current : visibleData?.markers[0]?.id));
  }, [visibleData?.markers]);

  const activeMarker = useMemo(() => {
    const markers = visibleData?.markers ?? [];
    return markers.find((marker) => marker.id === selectedId) ?? hovered ?? markers[0];
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
        description: "Created from the map-centric workbench",
        listing_ids: listingIds,
        filters: {
          ...filters,
          only_watchlisted: onlyWatchlisted,
          only_memo_ready: onlyMemoReady,
          only_comp_ready: onlyCompReady,
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["workbench"] });
      void queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] });
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workbench"] }),
  });
  const createMemo = useMutation({
    mutationFn: (listingId: string) =>
      api.createMemo({
        title: `${memoTitle} ${new Date().toISOString().slice(11, 19)}`,
        listing_id: listingId,
        assumptions: ["Created from the map workbench selection"],
        risks: ["Source and support state should be reviewed before export"],
        sections: [
          {
            heading: "Workbench selection",
            body: "This memo started from a map-driven exploration flow.",
          },
        ],
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] }),
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
    onSuccess: (_, listingId) => navigate(`/comp-reviews/${listingId}`),
  });
  const runValuation = useMutation({
    mutationFn: (listingId: string) => api.createValuation({ listing_id: listingId, persist: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workbench"] });
      await queryClient.invalidateQueries({ queryKey: ["listing-context", activeMarker?.id] });
    },
  });

  const columnHelper = createColumnHelper<TableRow>();
  const columns = useMemo(
    () => [
      columnHelper.accessor("title", {
        header: "Listing",
        cell: (info) => String(info.getValue() ?? ""),
      }),
      columnHelper.accessor("ask_price", {
        header: "Ask",
        cell: (info) => fmtMoney(info.getValue() as number | null),
      }),
      columnHelper.accessor("fair_value", {
        header: "Fair value",
        cell: (info) => fmtMoney(info.getValue() as number | null),
      }),
      columnHelper.accessor("support", {
        header: "Support",
        cell: (info) => fmtPct(info.getValue() as number | null),
      }),
      columnHelper.accessor("source_status", {
        header: "Source",
        cell: (info) => String(info.getValue() ?? ""),
      }),
      columnHelper.accessor("next_action", {
        header: "Next action",
        cell: (info) => String(info.getValue() ?? ""),
      }),
    ],
    [columnHelper],
  );

  const table = useReactTable({
    data: visibleData?.table_rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const selectedContext = contextQuery.data as ListingContextResponse | undefined;
  const layerItems = layersQuery.data?.overlays ?? [];
  const loading = exploreQuery.isLoading || layersQuery.isLoading;
  const error = exploreQuery.error || layersQuery.error;
  const selectedBasket = selectedIds.length > 0 ? selectedIds : activeMarker ? [activeMarker.id] : [];

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
    return <div className="page-card">Loading map-centric workbench…</div>;
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
          <p className="eyebrow">Analyst dense mode</p>
          <h2>Spatial triage first</h2>
          <p>
            The map is the primary exploration surface. Filters, saved lenses, and source states now
            orbit around location rather than the old table-first workflow.
          </p>
        </div>

        <div className="rail-section">
          <span className="eyebrow">Search lens</span>
          <label>
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="City, title, source, memo…"
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
          <div className="form-stack">
            <label><input type="checkbox" checked={onlyWatchlisted} onChange={() => setOnlyWatchlisted((value) => !value)} /> Only watchlisted</label>
            <label><input type="checkbox" checked={onlyMemoReady} onChange={() => setOnlyMemoReady((value) => !value)} /> Memo-linked only</label>
            <label><input type="checkbox" checked={onlyCompReady} onChange={() => setOnlyCompReady((value) => !value)} /> Comp-review only</label>
          </div>
          <div className="toggle-row">
            <label><input type="checkbox" checked={showHeat} onChange={() => setShowHeat((value) => !value)} /> Density heat</label>
            <label><input type="checkbox" checked={showLabels} onChange={() => setShowLabels((value) => !value)} /> Delta labels</label>
          </div>
        </div>

        <div className="rail-section">
          <span className="eyebrow">Save current lens</span>
          <label>
            Saved search name
            <input value={savedSearchName} onChange={(event) => setSavedSearchName(event.target.value)} />
          </label>
          <button className="ghost-button" onClick={() => createSavedSearch.mutate()} disabled={createSavedSearch.isPending}>
            Save lens
          </button>
        </div>

        <div className="rail-section">
          <span className="eyebrow">Layer semantics</span>
          <div className="legend-list">
            {layerItems.map((layer) => (
              <div key={layer.id} className={`legend-item ${layer.blocked ? "is-blocked" : ""}`}>
                <strong>{layer.label}</strong>
                <p>{layer.description}</p>
                {layer.blocked ? <span>Blocked: {layer.blocked_reason}</span> : null}
              </div>
            ))}
          </div>
        </div>
      </aside>

      <main className="center-stage">
        <div className="topbar-card">
          <div>
            <span className="eyebrow">Map-centric workbench</span>
            <h2>Spatial exploration drives the workflow</h2>
            <p>
              Marker size shows value opportunity, color shows source/support state, and the dock stays
              synchronized with selection instead of competing with it.
            </p>
          </div>
          <div className="topbar-actions">
            <Link className="nav-chip" to="/pipeline">Pipeline</Link>
            <Link className="nav-chip" to="/watchlists">Watchlists</Link>
            <Link className="nav-chip" to="/memos">Memos</Link>
          </div>
        </div>

        <div className="stats-grid">
          {sectionTitle("Tracked", String(visibleData.stats.tracked), "Listings in the current local corpus")}
          {sectionTitle("Visible", String(visibleData.stats.visible), "Assets matching the active map lens")}
          {sectionTitle("Valuation-ready", String(visibleData.stats.valuation_ready_count), "Listings with enough fields to run valuation")}
          {sectionTitle("Valued", String(visibleData.stats.available_count), "Listings with cached valuation support in view")}
        </div>

        {visibleData.stats.visible > 0 && visibleData.stats.available_count === 0 ? (
          <div className="warning-card">
            No cached valuations are available in the current lens. Broaden the map filters or run valuation on a ready
            listing from the dossier rail.
          </div>
        ) : null}

        {selectedIds.length > 1 ? (
          <div className="selection-banner">
            <strong>{selectedIds.length} listings selected</strong>
            <p>Use shift-click on the map or table to build a review basket for watchlists and triage.</p>
          </div>
        ) : null}

        <WorkbenchMap
          markers={visibleData.markers}
          selectedId={activeMarker?.id}
          selectedIds={selectedIds}
          showHeat={showHeat}
          showLabels={showLabels}
          onSelect={handleSelect}
          onHover={setHovered}
        />

        <div className="selection-dock">
          <div className="dock-header">
            <div>
              <h3>Listings dock</h3>
              <p>Shift-click to build a basket. Single click to pin the active dossier.</p>
            </div>
            <div className="chip-row">
              <span className="chip">{selectedIds.length} pinned</span>
              <span className="chip">{visibleData.stats.unavailable_count} unavailable</span>
              <span className="chip">{visibleData.stats.degraded_source_count} degraded</span>
            </div>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <th key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => {
                  const rowId = String(row.original.id);
                  return (
                    <tr
                      key={row.id}
                      className={[
                        rowId === activeMarker?.id ? "is-selected" : "",
                        selectedIds.includes(rowId) ? "is-basketed" : "",
                      ].filter(Boolean).join(" ")}
                      onClick={(event) => handleSelect(rowId, { multi: event.shiftKey || event.metaKey || event.ctrlKey })}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <aside className="right-rail">
        <div className="rail-section">
          <span className="eyebrow">Selected listing</span>
          {activeMarker ? (
            <>
              <h3>{activeMarker.title}</h3>
              <p>
                {activeMarker.city}, {activeMarker.country}
              </p>
              <div className="support-row">
                <span className={getStatusClass(activeMarker.source_status)}>{activeMarker.source_status}</span>
                <span className={getStatusClass(activeMarker.valuation_status)}>{activeMarker.valuation_status}</span>
                {activeMarker.watchlisted ? <span className="status-pill status-draft">watchlisted</span> : null}
              </div>
              <div className="metric-grid">
                {sectionTitle("Ask", fmtMoney(activeMarker.ask_price))}
                {sectionTitle("Fair value", fmtMoney(activeMarker.fair_value))}
                {sectionTitle("Support", fmtPct(activeMarker.support))}
                {sectionTitle("Value delta", fmtPct(activeMarker.value_delta_pct))}
              </div>
              {activeMarker.valuation_reason ? (
                <div className="warning-card">{formatValuationReason(activeMarker.valuation_reason)}</div>
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
                  Save selection to watchlist
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
                <Link className="ghost-button link-button" to={`/listings/${activeMarker.id}`}>
                  Open dossier
                </Link>
              </div>
            </>
          ) : (
            <p>Select a marker to open the dossier rail.</p>
          )}
        </div>

        <div className="rail-section">
          <span className="eyebrow">Alerts + jobs</span>
          <div className="timeline">
            {(visibleData.alerts ?? []).slice(0, 5).map((alert) => (
              <div key={String(alert.id)} className="timeline-item">
                <strong>{formatMaybeString(alert.code, "alert")}</strong>
                <p>{formatMaybeString(alert.source_id, "unknown source")}</p>
              </div>
            ))}
            {(visibleData.jobs ?? []).slice(0, 3).map((job) => (
              <div key={String(job.id)} className="timeline-item">
                <strong>{formatMaybeString(job.job_type, "job")}</strong>
                <p>{formatMaybeString(job.status, "queued")}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rail-section">
          <span className="eyebrow">Saved lenses</span>
          <div className="list-stack">
            {(visibleData.saved_searches ?? []).slice(0, 5).map((item) => (
              <div key={String(item.id)} className="list-card">
                <strong>{formatMaybeString(item.name, "Saved lens")}</strong>
                <p>{formatMaybeString(item.query, "Local map lens")}</p>
              </div>
            ))}
          </div>
        </div>

        {selectedContext ? (
          <div className="rail-section">
            <span className="eyebrow">Listing context</span>
            <p>Next action: {selectedContext.next_action}</p>
            <div className="timeline">
              {(selectedContext.quality_events ?? []).slice(0, 4).map((event) => (
                <div key={String(event.id)} className="timeline-item">
                  <strong>{formatMaybeString(event.code, "event")}</strong>
                  <p>{formatMaybeString(event.severity, "status")}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
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
  if (contextQuery.isLoading) return <div className="page-card">Loading listing context…</div>;
  if (!context) return <div className="page-card error-state">Listing context unavailable.</div>;
  const listing = context.listing as Record<string, unknown>;
  const valuation = context.valuation as Record<string, unknown>;
  const location = (listing.location as Record<string, unknown> | undefined) ?? {};
  return (
    <div className="page-card">
      <span className="eyebrow">Listing detail</span>
      <h2>{formatMaybeString(listing.title, listingId)}</h2>
      <p>
        {formatMaybeString(location.city, "")} {formatMaybeString(location.country, "")}
      </p>
      <div className="metric-grid">
        {sectionTitle("Ask", fmtMoney((listing.price as number | undefined) ?? null))}
        {sectionTitle("Fair value", fmtMoney((valuation.fair_value as number | undefined) ?? null))}
        {sectionTitle("Support", fmtPct((valuation.support as number | undefined) ?? null))}
        {sectionTitle("Status", String(valuation.valuation_status ?? "unknown"))}
      </div>
      {context.serving_reason ? <div className="warning-card">{formatValuationReason(context.serving_reason)}</div> : null}
      {valuation.reason ? <div className="warning-card">{formatValuationReason(valuation.reason)}</div> : null}
      <div className="section-split">
        <div className="list-stack">
          <div className="list-card">
            <strong>Next action</strong>
            <p>{context.next_action}</p>
          </div>
          <div className="list-card">
            <strong>Source status</strong>
            <p>{formatMaybeString(context.source_status.status)}</p>
          </div>
          <div className="list-card">
            <strong>Serving state</strong>
            <p>{context.serving_eligible ? "Eligible" : formatValuationReason(context.serving_reason)}</p>
          </div>
          <div className="list-card">
            <strong>Valuation readiness</strong>
            <p>{context.valuation_ready ? "Ready" : "Missing required fields"}</p>
          </div>
          {context.can_run_valuation ? (
            <button className="primary-button" onClick={() => runValuation.mutate()} disabled={runValuation.isPending}>
              Run valuation now
            </button>
          ) : null}
        </div>
        <div className="list-stack">
          {(context.memos ?? []).map((memo) => (
            <div key={String(memo.id)} className="list-card">
              <strong>{formatMaybeString(memo.title, "Memo")}</strong>
              <p>{formatMaybeString(memo.status, "draft")}</p>
            </div>
          ))}
          {(context.comp_reviews ?? []).map((review) => (
            <div key={String(review.id)} className="list-card">
              <strong>Comp review</strong>
              <p>{formatMaybeString(review.status, "draft")}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CompReviewPage() {
  const { listingId = "" } = useParams();
  const [notes, setNotes] = useState("Manual comp adjustment requested from the map workbench.");
  const reviewsQuery = useQuery({
    queryKey: ["comp-reviews", listingId],
    queryFn: () => api.compReviews(listingId),
  });
  const createReview = useMutation({
    mutationFn: () =>
      api.createCompReview({
        listing_id: listingId,
        status: "draft",
        selected_comp_ids: [],
        rejected_comp_ids: [],
        overrides: { analyst_note: notes },
        notes,
      }),
  });
  return (
    <div className="page-card">
      <span className="eyebrow">Comp workbench</span>
      <h2>Comp review for {listingId}</h2>
      <label>
        Override note
        <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} />
      </label>
      <button className="primary-button" onClick={() => createReview.mutate()} disabled={createReview.isPending}>
        Create new comp review
      </button>
      <div className="list-stack">
        {(reviewsQuery.data?.items ?? []).map((review) => (
          <div key={String(review.id)} className="list-card">
            <strong>{formatMaybeString(review.status, "draft")}</strong>
            <p>{JSON.stringify(review.overrides ?? {})}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MemosPage() {
  const memosQuery = useQuery({ queryKey: ["memos"], queryFn: api.memos });
  const exportMutation = useMutation({
    mutationFn: (memoId: string) => api.exportMemo(memoId),
  });
  return (
    <div className="page-card">
      <span className="eyebrow">Memos</span>
      <h2>Memo queue</h2>
      <div className="list-stack">
        {(memosQuery.data?.items ?? []).map((memo) => (
          <div key={String(memo.id)} className="list-card">
            <strong>{formatMaybeString(memo.title, "Memo")}</strong>
            <p>{formatMaybeString(memo.status, "draft")}</p>
            <button className="ghost-button" onClick={() => exportMutation.mutate(String(memo.id))}>
              Export memo
            </button>
          </div>
        ))}
      </div>
      {exportMutation.data ? (
        <pre className="export-card">{formatMaybeString(exportMutation.data.content, "")}</pre>
      ) : null}
    </div>
  );
}

export function WatchlistsPage() {
  const watchlistsQuery = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists });
  const searchesQuery = useQuery({ queryKey: ["saved-searches"], queryFn: api.savedSearches });
  return (
    <div className="page-card two-column-page">
      <section>
        <span className="eyebrow">Watchlists</span>
        <h2>Tracked property groups</h2>
        <div className="list-stack">
          {(watchlistsQuery.data?.items ?? []).map((watchlist) => (
            <div key={String(watchlist.id)} className="list-card">
              <strong>{formatMaybeString(watchlist.name, "Watchlist")}</strong>
              <p>{formatMaybeString(watchlist.description, "")}</p>
            </div>
          ))}
        </div>
      </section>
      <section>
        <span className="eyebrow">Saved searches</span>
        <h2>Reusable lenses</h2>
        <div className="list-stack">
          {(searchesQuery.data?.items ?? []).map((searchItem) => (
            <div key={String(searchItem.id)} className="list-card">
              <strong>{formatMaybeString(searchItem.name, "Lens")}</strong>
              <p>{JSON.stringify(searchItem.filters ?? {})}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function PipelinePage() {
  const pipelineQuery = useQuery({ queryKey: ["pipeline"], queryFn: api.pipeline });
  const sourcesQuery = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  const coverageQuery = useQuery({ queryKey: ["coverage"], queryFn: api.coverage });
  const qualityQuery = useQuery({ queryKey: ["quality"], queryFn: api.quality });
  const benchmarkQuery = useQuery({ queryKey: ["benchmarks"], queryFn: api.benchmarks });

  const sourceSummary = (sourcesQuery.data?.summary as Record<string, number> | undefined) ?? {};

  return (
    <div className="page-card">
      <span className="eyebrow">Pipeline + source health</span>
      <h2>Operational trust surface</h2>
      <div className="metric-grid">
        {sectionTitle("Needs refresh", String(Boolean(pipelineQuery.data?.needs_refresh) ? "yes" : "no"))}
        {sectionTitle("Supported", String(sourceSummary.supported ?? 0))}
        {sectionTitle("Blocked", String(sourceSummary.blocked ?? 0))}
        {sectionTitle("Benchmark runs", String(benchmarkQuery.data?.total ?? 0))}
      </div>
      <div className="two-column-page">
        <section>
          <h3>Recent jobs</h3>
          <div className="list-stack">
            {(jobsQuery.data?.items ?? []).map((job) => (
              <div key={String(job.id)} className="list-card">
                <strong>{formatMaybeString(job.job_type, "job")}</strong>
                <p>{formatMaybeString(job.status, "")}</p>
              </div>
            ))}
          </div>
        </section>
        <section>
          <h3>Coverage</h3>
          <div className="list-stack">
            {(coverageQuery.data?.items ?? []).map((item) => (
              <div key={String(item.id)} className="list-card">
                <strong>{formatMaybeString(item.segment_key, "segment")}</strong>
                <p>{formatMaybeString(item.status, "")}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
      <h3>Data quality events</h3>
      <div className="timeline">
        {(qualityQuery.data?.items ?? []).slice(0, 8).map((item) => (
          <div key={String(item.id)} className="timeline-item">
            <strong>{formatMaybeString(item.code, "event")}</strong>
            <p>{formatMaybeString(item.source_id, "")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CommandCenterPage() {
  const runsQuery = useQuery({ queryKey: ["command-runs"], queryFn: api.commandRuns });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  return (
    <div className="page-card two-column-page">
      <section>
        <span className="eyebrow">Command Center</span>
        <h2>Advisory run history</h2>
        <div className="list-stack">
          {(runsQuery.data?.items ?? []).map((run) => (
            <div key={String(run.id)} className="list-card">
              <strong>{formatMaybeString(run.query, "Run")}</strong>
              <p>{formatMaybeString(run.status, "")}</p>
            </div>
          ))}
        </div>
      </section>
      <section>
        <span className="eyebrow">Job handoff</span>
        <h2>Recent execution</h2>
        <div className="list-stack">
          {(jobsQuery.data?.items ?? []).map((job) => (
            <div key={String(job.id)} className="list-card">
              <strong>{formatMaybeString(job.job_type, "job")}</strong>
              <p>{formatMaybeString(job.status, "")}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
