import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { fmtMoney, fmtPct, fmtDateTime, formatMaybeString, formatMetricValue } from "../format";
import { track } from "../track";
import { statusBadge } from "../components/StatusBadge";

type Tab = "overview" | "evidence" | "media" | "market" | "history";

export function ListingDetailPage() {
  const { listingId = "" } = useParams();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  const contextQuery = useQuery({
    queryKey: ["listing-context", listingId],
    queryFn: () => api.listingContext(listingId),
  });

  const runValuation = useMutation({
    mutationFn: () => api.createValuation({ listing_id: listingId, persist: true }),
    onSuccess: async () => {
      track({ event_name: "listing_valuation_run", route: `/listings/${listingId}`, subject_type: "listing", subject_id: listingId });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["listing-context", listingId] }),
        queryClient.invalidateQueries({ queryKey: ["workbench"] }),
      ]);
    },
  });

  if (contextQuery.isLoading) {
    return (
      <div className="detail-max">
        <div className="card card-centered">
          <p style={{ color: "var(--text-secondary)" }}>Loading listing...</p>
        </div>
      </div>
    );
  }

  const context = contextQuery.data;
  if (!context) {
    return (
      <div className="detail-max">
        <div className="card card-centered">
          <p style={{ color: "var(--accent-danger)" }}>Listing not found.</p>
          <Link to="/" className="btn btn-secondary" style={{ marginTop: "var(--space-3)" }}>Back to map</Link>
        </div>
      </div>
    );
  }

  const listing = context.listing;
  const location = listing.location;
  const valuation = context.valuation;

  const TABS: Array<{ id: Tab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "evidence", label: "Evidence" },
    { id: "media", label: `Media (${context.media_summary.count})` },
    { id: "market", label: "Market" },
    { id: "history", label: "History" },
  ];

  return (
    <div className="detail-max">
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link to="/">Map</Link>
        <span className="sep" />
        <span>{listing.title}</span>
      </div>

      {/* Header */}
      <div className="page-header">
        <div className="page-header-info">
          <h1>{listing.title}</h1>
          <p>
            {formatMaybeString(location?.city)}
            {location?.country ? `, ${location.country}` : ""}
            {listing.property_type ? ` \u00B7 ${listing.property_type}` : ""}
            {listing.bedrooms != null ? ` \u00B7 ${listing.bedrooms} bed` : ""}
            {listing.surface_area_sqm != null ? ` \u00B7 ${listing.surface_area_sqm} sqm` : ""}
          </p>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-1)" }}>
            {statusBadge(context.source_health.status)}
            {statusBadge(valuation.valuation_status)}
          </div>
        </div>
        <div className="page-header-actions">
          {context.can_run_valuation && (
            <button className="btn btn-primary" onClick={() => runValuation.mutate()} disabled={runValuation.isPending}>
              Run valuation
            </button>
          )}
          <Link to={`/listings/${listingId}/comps`} className="btn btn-secondary">Comp review</Link>
          <Link to="/library" className="btn btn-ghost">Library</Link>
        </div>
      </div>

      {/* Key metrics */}
      <div className="metrics-row">
        <div className="card">
          <div className="metric">
            <span className="metric-label">Ask price</span>
            <span className="metric-value">{fmtMoney(listing.price, listing.currency)}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Fair value</span>
            <span className="metric-value">{fmtMoney(valuation.fair_value)}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Support</span>
            <span className="metric-value">{fmtPct(valuation.support)}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Value delta</span>
            <span className="metric-value">{fmtPct(valuation.value_delta_pct)}</span>
          </div>
        </div>
      </div>

      {/* Data gaps */}
      {context.data_gaps.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
          {context.data_gaps.map((gap) => (
            <div key={gap.code} className={`data-gap-inline severity-${gap.severity}`}>
              <strong>{gap.label}</strong>
              {gap.detail && <span>&mdash; {gap.detail}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="tab-bar">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab-btn${activeTab === tab.id ? " is-active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <>
          <div className="card">
            <div className="section-header">
              <h3>Decision summary</h3>
              {statusBadge(context.source_health.status)}
            </div>
            <div className="kv-list" style={{ marginBottom: "var(--space-4)" }}>
              <div className="kv-item"><dt>Value delta</dt><dd>{fmtPct(valuation.value_delta_pct)}</dd></div>
              <div className="kv-item"><dt>Projected 12m</dt><dd>{fmtMoney(valuation.projected_value_12m)}</dd></div>
              <div className="kv-item"><dt>Range low</dt><dd>{fmtMoney(valuation.price_range_low)}</dd></div>
              <div className="kv-item"><dt>Range high</dt><dd>{fmtMoney(valuation.price_range_high)}</dd></div>
              <div className="kv-item"><dt>Yield</dt><dd>{fmtPct(valuation.yield_pct)}</dd></div>
              <div className="kv-item"><dt>Uncertainty</dt><dd>{fmtPct(valuation.uncertainty_pct)}</dd></div>
            </div>
            <p className="text-muted">
              {context.evidence_summary.thesis || "No valuation thesis persisted yet."}
            </p>
          </div>

          <div className="card">
            <h3 style={{ marginBottom: "var(--space-3)" }}>Linked artifacts</h3>
            <div style={{ display: "flex", gap: "var(--space-4)", fontSize: "var(--text-sm)" }}>
              <span><strong>{context.watchlists.length}</strong> watchlists</span>
              <span><strong>{context.memos.length}</strong> memos</span>
              <span><strong>{context.comp_reviews.length}</strong> comp reviews</span>
            </div>
          </div>
        </>
      )}

      {activeTab === "evidence" && (
        <div className="card">
          <div className="section-header">
            <h3>Comparable evidence</h3>
            <span className="chip-v2">{context.evidence_summary.comp_count} comps ({context.evidence_summary.sold_comp_count} sold)</span>
          </div>
          {context.evidence_summary.model_used && (
            <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-4)", fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
              <span>Model: {context.evidence_summary.model_used}</span>
              <span>Calibration: {formatMaybeString(context.evidence_summary.calibration_status)}</span>
            </div>
          )}
          {context.evidence_summary.top_comps.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Adj price</th>
                  <th>Similarity</th>
                  <th>Sold</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {context.evidence_summary.top_comps.map((comp) => (
                  <tr key={comp.id} style={{ cursor: "default" }}>
                    <td>{comp.id.slice(0, 8)}...</td>
                    <td className="mono">{fmtMoney(comp.adj_price)}</td>
                    <td className="mono">{fmtPct(comp.similarity_score)}</td>
                    <td>{comp.is_sold ? "Sold" : "Active"}</td>
                    <td className="mono">{comp.attention_weight?.toFixed(3) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state-v2" style={{ padding: "var(--space-8) 0" }}>
              <h3>No comp evidence</h3>
              <p>Run a valuation to generate comparable evidence.</p>
            </div>
          )}

          {Object.keys(context.evidence_summary.confidence_components).length > 0 && (
            <>
              <h3 style={{ margin: "var(--space-5) 0 var(--space-3)" }}>Confidence breakdown</h3>
              <div className="kv-list">
                {Object.entries(context.evidence_summary.confidence_components).map(([key, value]) => (
                  <div key={key} className="kv-item">
                    <dt>{key.replace(/_/g, " ")}</dt>
                    <dd>{formatMetricValue(value)}</dd>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === "media" && (
        <div className="card">
          {context.media_summary.image_urls.length > 0 ? (
            <div className="media-grid-v2">
              {context.media_summary.image_urls.slice(0, 9).map((url) => (
                <img key={url} src={url} alt={listing.title} />
              ))}
            </div>
          ) : (
            <div className="empty-state-v2" style={{ padding: "var(--space-8) 0" }}>
              <h3>No images</h3>
              <p>This listing has no imagery available.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === "market" && (
        <div className="card">
          <div className="kv-list" style={{ marginBottom: "var(--space-4)" }}>
            <div className="kv-item"><dt>Text sentiment</dt><dd>{context.market_context.text_sentiment?.toFixed(2) ?? "N/A"}</dd></div>
            <div className="kv-item"><dt>Image sentiment</dt><dd>{context.market_context.image_sentiment?.toFixed(2) ?? "N/A"}</dd></div>
            <div className="kv-item"><dt>Listed at</dt><dd>{fmtDateTime(context.market_context.listed_at)}</dd></div>
            <div className="kv-item"><dt>Updated at</dt><dd>{fmtDateTime(context.market_context.updated_at)}</dd></div>
          </div>

          {context.market_context.tags.length > 0 && (
            <div style={{ display: "flex", gap: "var(--space-1)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
              {context.market_context.tags.map((tag) => (
                <span key={tag} className="chip-v2">{tag}</span>
              ))}
            </div>
          )}

          {Object.keys(context.market_context.signals).length > 0 && (
            <>
              <h3 style={{ margin: "var(--space-3) 0" }}>Market signals</h3>
              <div className="kv-list">
                {Object.entries(context.market_context.signals).map(([key, value]) => (
                  <div key={key} className="kv-item">
                    <dt>{key.replace(/_/g, " ")}</dt>
                    <dd>{formatMetricValue(value)}</dd>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === "history" && (
        <>
          <div className="card">
            <h3 style={{ marginBottom: "var(--space-3)" }}>Source health</h3>
            <div className="kv-list" style={{ marginBottom: "var(--space-4)" }}>
              <div className="kv-item"><dt>Status</dt><dd>{context.source_health.status}</dd></div>
              <div className="kv-item"><dt>Last contract</dt><dd>{fmtDateTime(context.source_health.last_contract_at)}</dd></div>
              <div className="kv-item"><dt>Last quality event</dt><dd>{fmtDateTime(context.source_health.last_quality_event_at)}</dd></div>
            </div>
            {context.source_health.reasons.length > 0 && (
              <p className="text-muted">
                Reasons: {context.source_health.reasons.join(", ")}
              </p>
            )}
          </div>

          {context.provenance_timeline.length > 0 && (
            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Provenance timeline</h3>
              <div className="timeline-v2">
                {context.provenance_timeline.map((event) => (
                  <div key={event.id} className="timeline-v2-item">
                    <strong>{event.title}</strong>
                    <p>{event.detail}</p>
                    <p>{fmtDateTime(event.at)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {context.quality_events.length > 0 && (
            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Quality events</h3>
              <div className="timeline-v2">
                {context.quality_events.map((event) => (
                  <div key={event.id} className="timeline-v2-item">
                    <strong>{event.code}</strong>
                    <p>{event.severity} &middot; {formatMaybeString(event.source_id, "unknown source")}</p>
                    <p>{fmtDateTime(event.created_at)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
