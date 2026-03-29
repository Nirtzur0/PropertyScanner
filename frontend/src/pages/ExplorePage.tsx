import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { fmtMoney, fmtPct } from "../format";
import { track } from "../track";
import { statusBadge } from "../components/StatusBadge";
import { useExploreFilters } from "../hooks/useExploreFilters";
import { useSelection } from "../hooks/useSelection";
import { WorkbenchMap } from "../components/WorkbenchMap";
import type { WorkbenchTableRow } from "../types";

export function ExplorePage() {
  const queryClient = useQueryClient();
  const filterState = useExploreFilters();
  const selection = useSelection();
  const [showMap, setShowMap] = useState(true);
  const [watchlistName, setWatchlistName] = useState("");
  const noop = useCallback(() => {}, []);

  const exploreQuery = useQuery({
    queryKey: ["workbench", filterState.filters],
    queryFn: () => api.explore(filterState.filters),
  });

  const data = exploreQuery.data;
  const stats = data?.stats;
  const tableRows = data?.table_rows ?? [];
  const markers = data?.markers ?? [];

  const activePills = useMemo(() => {
    const pills: Array<{ label: string; clear: () => void }> = [];
    if (filterState.country) pills.push({ label: `Country: ${filterState.country}`, clear: () => filterState.setCountry("") });
    if (filterState.city) pills.push({ label: `City: ${filterState.city}`, clear: () => filterState.setCity("") });
    if (filterState.listingType) pills.push({ label: `Type: ${filterState.listingType}`, clear: () => filterState.setListingType("") });
    if (filterState.minPrice) pills.push({ label: `Min: ${filterState.minPrice}`, clear: () => filterState.setMinPrice("") });
    if (filterState.maxPrice) pills.push({ label: `Max: ${filterState.maxPrice}`, clear: () => filterState.setMaxPrice("") });
    if (filterState.minSupport) pills.push({ label: `Support: ${filterState.minSupport}+`, clear: () => filterState.setMinSupport("") });
    if (filterState.sourceStatus) pills.push({ label: `Source: ${filterState.sourceStatus}`, clear: () => filterState.setSourceStatus("") });
    return pills;
  }, [filterState.country, filterState.city, filterState.listingType, filterState.minPrice, filterState.maxPrice, filterState.minSupport, filterState.sourceStatus]);

  const createWatchlist = useMutation({
    mutationFn: (listingIds: string[]) =>
      api.createWatchlist({
        name: watchlistName || `Watchlist ${new Date().toISOString().slice(0, 10)}`,
        listing_ids: listingIds,
        filters: filterState.filters,
      }),
    onSuccess: () => {
      track({ event_name: "watchlist_created", route: "/explore", subject_type: "watchlist" });
      void queryClient.invalidateQueries({ queryKey: ["workbench"] });
      void queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      selection.clear();
      setWatchlistName("");
    },
  });

  if (exploreQuery.isLoading) {
    return (
      <div className="page-container">
        <div className="card card-centered">
          <p style={{ color: "var(--text-secondary)" }}>Loading properties...</p>
        </div>
      </div>
    );
  }

  if (exploreQuery.error) {
    return (
      <div className="page-container">
        <div className="card card-centered">
          <p style={{ color: "var(--accent-danger)" }}>
            {exploreQuery.error instanceof Error ? exploreQuery.error.message : "Failed to load data."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      {/* Filter bar */}
      <div className="filter-bar">
        <label>
          Search
          <input
            className="filter-search"
            value={filterState.search}
            onChange={(e) => filterState.setSearch(e.target.value)}
            placeholder="City, listing, source..."
          />
        </label>
        <label>
          Country
          <input
            className="filter-short"
            value={filterState.country}
            onChange={(e) => filterState.setCountry(e.target.value.toUpperCase())}
            placeholder="ES"
          />
        </label>
        <label>
          City
          <input
            className="filter-short"
            value={filterState.city}
            onChange={(e) => filterState.setCity(e.target.value)}
            placeholder="Madrid"
          />
        </label>
        <label>
          Type
          <select className="filter-select" value={filterState.listingType} onChange={(e) => filterState.setListingType(e.target.value)}>
            <option value="">Any</option>
            <option value="sale">Sale</option>
            <option value="rent">Rent</option>
          </select>
        </label>
        <label>
          Min price
          <input className="filter-short" type="number" min="0" step="1000" value={filterState.minPrice} onChange={(e) => filterState.setMinPrice(e.target.value)} placeholder="0" />
        </label>
        <label>
          Max price
          <input className="filter-short" type="number" min="0" step="1000" value={filterState.maxPrice} onChange={(e) => filterState.setMaxPrice(e.target.value)} placeholder="∞" />
        </label>
        <label>
          Support
          <input className="filter-short" type="number" min="0" max="1" step="0.01" value={filterState.minSupport} onChange={(e) => filterState.setMinSupport(e.target.value)} placeholder="0" />
        </label>
        <label>
          Source
          <select className="filter-select" value={filterState.sourceStatus} onChange={(e) => filterState.setSourceStatus(e.target.value)}>
            <option value="">Any</option>
            <option value="supported">Supported</option>
            <option value="degraded">Degraded</option>
            <option value="experimental">Experimental</option>
            <option value="blocked">Blocked</option>
          </select>
        </label>
        <button className="btn btn-ghost btn-sm" onClick={() => setShowMap((v) => !v)}>
          {showMap ? "Hide map" : "Show map"}
        </button>
      </div>

      {/* Active filter pills */}
      {activePills.length > 0 && (
        <div className="filter-pills">
          {activePills.map((pill) => (
            <button key={pill.label} className="filter-pill" onClick={pill.clear}>
              {pill.label} &times;
            </button>
          ))}
          <button className="filter-pill" onClick={filterState.clearFilters}>
            Clear all &times;
          </button>
        </div>
      )}

      {/* Stats row */}
      <div className="stats-row">
        <span><strong>{stats?.tracked ?? 0}</strong> tracked</span>
        <span><strong>{stats?.visible ?? 0}</strong> visible</span>
        <span><strong>{stats?.watchlist_hits ?? 0}</strong> watchlisted</span>
        <span><strong>{stats?.degraded_source_count ?? 0}</strong> degraded</span>
        <span><strong>{stats?.valuation_ready_count ?? 0}</strong> valuation ready</span>
      </div>

      {/* Map */}
      {showMap && markers.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden", height: 480 }}>
          <WorkbenchMap
            markers={markers}
            selectedId={undefined}
            selectedIds={selection.selectedIds}
            showHeat={false}
            showLabels={false}
            onSelect={(id, opts) => opts.multi ? selection.toggle(id) : selection.selectOnly(id)}
            onHover={noop}
          />
        </div>
      )}

      {/* Data table */}
      <div className="card" style={{ padding: 0 }}>
        {tableRows.length === 0 ? (
          <div className="empty-state-v2">
            <h3>No listings found</h3>
            <p>Try adjusting your filters or run a crawl to populate the database.</p>
          </div>
        ) : (
          <div style={{ overflow: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th className="checkbox-cell" />
                  <th>Listing</th>
                  <th>City</th>
                  <th>Ask</th>
                  <th>Fair value</th>
                  <th>Support</th>
                  <th>Source</th>
                  <th>Valuation</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row: WorkbenchTableRow) => (
                  <tr
                    key={row.id}
                    className={selection.isSelected(row.id) ? "is-selected" : ""}
                  >
                    <td className="checkbox-cell" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selection.isSelected(row.id)}
                        onChange={() => selection.toggle(row.id)}
                      />
                    </td>
                    <td>
                      <Link
                        to={`/listings/${row.id}`}
                        style={{ color: "inherit", textDecoration: "none", fontWeight: 500 }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {row.title}
                      </Link>
                    </td>
                    <td>{row.city ?? "—"}</td>
                    <td className="mono">{fmtMoney(row.ask_price)}</td>
                    <td className="mono">{fmtMoney(row.fair_value)}</td>
                    <td className="mono">{fmtPct(row.support)}</td>
                    <td>{statusBadge(row.source_status)}</td>
                    <td>{statusBadge(row.valuation_status)}</td>
                    <td className="text-muted-xs">{row.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Floating action bar */}
      {selection.count > 0 && (
        <div className="floating-action-bar">
          <span className="fab-count">{selection.count} selected</span>
          <input
            value={watchlistName}
            onChange={(e) => setWatchlistName(e.target.value)}
            placeholder="Watchlist name..."
            style={{
              background: "rgba(255,255,255,0.1)",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-inverse)",
              height: 28,
              padding: "0 var(--space-2)",
              fontSize: "var(--text-xs)",
              width: 160,
            }}
          />
          <button
            className="btn btn-sm"
            onClick={() => createWatchlist.mutate(selection.selectedIds)}
            disabled={createWatchlist.isPending}
          >
            Add to watchlist
          </button>
          <button className="btn btn-sm" onClick={selection.clear}>
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
