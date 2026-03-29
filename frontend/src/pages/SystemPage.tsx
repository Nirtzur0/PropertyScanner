import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { fmtDateTime, fmtPct, formatMaybeString, formatMetricValue } from "../format";
import { statusBadge } from "../components/StatusBadge";
import { useState } from "react";

export function SystemPage() {
  const [showDetails, setShowDetails] = useState(false);
  const trustQuery = useQuery({ queryKey: ["pipeline-trust-summary"], queryFn: api.pipelineTrustSummary });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, staleTime: 15_000, enabled: showDetails });
  const benchmarkQuery = useQuery({ queryKey: ["benchmarks"], queryFn: api.benchmarks, enabled: showDetails });
  const qualityQuery = useQuery({ queryKey: ["quality"], queryFn: api.quality, enabled: showDetails });
  const coverageQuery = useQuery({ queryKey: ["coverage"], queryFn: api.coverage, enabled: showDetails });
  const contractQuery = useQuery({ queryKey: ["source-contract-runs"], queryFn: api.sourceContracts, enabled: showDetails });

  const trust = trustQuery.data;
  const counts = trust?.source_summary.counts ?? {};
  const isFresh = trust ? !trust.freshness.needs_refresh : true;

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-info">
          <h1>System</h1>
          <p>Pipeline health, source trust, and data quality.</p>
        </div>
      </div>

      {/* Trust banner */}
      <div className={`trust-banner ${isFresh ? "is-fresh" : "is-stale"}`}>
        <strong>{isFresh ? "Pipeline is fresh." : "Pipeline needs refresh."}</strong>
        <span>
          {counts.supported ?? 0} supported, {counts.degraded ?? 0} degraded, {counts.blocked ?? 0} blocked, {counts.experimental ?? 0} experimental.
          {trust?.top_blockers.length ? ` ${trust.top_blockers.length} active blocker(s).` : " No active blockers."}
        </span>
      </div>

      {/* Summary metrics */}
      <div className="metrics-row">
        <div className="card">
          <div className="metric">
            <span className="metric-label">Freshness</span>
            <span className="metric-value" style={{ fontSize: "var(--text-lg)" }}>{isFresh ? "Fresh" : "Stale"}</span>
            {trust?.freshness.reasons[0] && <span className="metric-note">{trust.freshness.reasons[0]}</span>}
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Running jobs</span>
            <span className="metric-value">{trust?.jobs_summary.running ?? 0}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Failed jobs</span>
            <span className="metric-value">{trust?.jobs_summary.failed ?? 0}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Benchmark</span>
            <span className="metric-value" style={{ fontSize: "var(--text-lg)" }}>
              {trust?.benchmark_gate.status ?? "No runs"}
            </span>
          </div>
        </div>
      </div>

      {/* Blockers + Sources */}
      <div className="two-col">
        <div className="card">
          <h3 style={{ marginBottom: "var(--space-3)" }}>Blockers</h3>
          {(trust?.top_blockers ?? []).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              {trust!.top_blockers.map((b) => (
                <div key={`${b.kind}-${b.title}`} style={{ padding: "var(--space-2) var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-md)" }}>
                  <div className="flex-between">
                    <strong style={{ fontSize: "var(--text-sm)" }}>{b.title}</strong>
                    {statusBadge(b.kind)}
                  </div>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginTop: 2 }}>{b.detail}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted">No active blockers.</p>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginBottom: "var(--space-3)" }}>Sources</h3>
          {(trust?.source_summary.top_sources ?? []).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              {trust!.source_summary.top_sources.map((s) => (
                <div key={s.source_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-2) 0", borderBottom: "1px solid var(--border-default)" }}>
                  <div>
                    <strong style={{ fontSize: "var(--text-sm)" }}>{s.name}</strong>
                    {s.reasons.length > 0 && (
                      <p className="text-muted-xs">{s.reasons.join(", ")}</p>
                    )}
                  </div>
                  {statusBadge(s.status ?? "unknown")}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted">No source data available.</p>
          )}
        </div>
      </div>

      {/* Quality events */}
      {(trust?.latest_quality_events ?? []).length > 0 && (
        <div className="card">
          <h3 style={{ marginBottom: "var(--space-3)" }}>Recent quality events</h3>
          <div className="timeline-v2">
            {trust!.latest_quality_events.map((e) => (
              <div key={e.id} className="timeline-v2-item">
                <strong>{e.code}</strong>
                <p>{formatMaybeString(e.source_id, "unknown")} &middot; {e.severity}</p>
                <p>{fmtDateTime(e.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Collapsible details */}
      <button className="btn btn-secondary" onClick={() => setShowDetails((v) => !v)}>
        {showDetails ? "Hide" : "Show"} operational details
      </button>

      {showDetails && (
        <>
          <div className="two-col">
            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Recent jobs</h3>
              {(jobsQuery.data?.items ?? []).length > 0 ? (
                jobsQuery.data!.items.slice(0, 8).map((job) => (
                  <div key={job.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-2) 0", borderBottom: "1px solid var(--border-default)" }}>
                    <div>
                      <strong style={{ fontSize: "var(--text-sm)" }}>{job.job_type}</strong>
                      <p className="text-muted-xs">{fmtDateTime(job.created_at)}</p>
                    </div>
                    {statusBadge(job.status)}
                  </div>
                ))
              ) : (
                <p className="text-muted">No job history.</p>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Coverage</h3>
              {(coverageQuery.data?.items ?? []).length > 0 ? (
                coverageQuery.data!.items.slice(0, 6).map((item) => (
                  <div key={item.id} style={{ padding: "var(--space-2) 0", borderBottom: "1px solid var(--border-default)", fontSize: "var(--text-sm)" }}>
                    <strong>{item.segment_key} &middot; {item.segment_value}</strong>
                    <p className="text-muted-xs">
                      {item.status} &middot; coverage {fmtPct(item.empirical_coverage)} &middot; sample {item.sample_size}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-muted">No coverage data.</p>
              )}
            </div>
          </div>

          <div className="two-col">
            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Quality stream</h3>
              {(qualityQuery.data?.items ?? []).length > 0 ? (
                <div className="timeline-v2">
                  {qualityQuery.data!.items.slice(0, 10).map((e) => (
                    <div key={e.id} className="timeline-v2-item">
                      <strong>{e.code}</strong>
                      <p>{formatMaybeString(e.source_id, "unknown")} &middot; {e.severity}</p>
                      <p>{fmtDateTime(e.created_at)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No quality events.</p>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Contract history</h3>
              {(contractQuery.data?.items ?? []).length > 0 ? (
                contractQuery.data!.items.slice(0, 8).map((item) => (
                  <div key={item.id} style={{ padding: "var(--space-2) 0", borderBottom: "1px solid var(--border-default)", fontSize: "var(--text-sm)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <strong>{item.source_id}</strong>
                      {statusBadge(item.status)}
                    </div>
                    <p className="text-muted-xs">{fmtDateTime(item.created_at)}</p>
                  </div>
                ))
              ) : (
                <p className="text-muted">No contract history.</p>
              )}
            </div>
          </div>

          {/* Benchmark detail */}
          {benchmarkQuery.data?.items[0] && (
            <div className="card">
              <h3 style={{ marginBottom: "var(--space-3)" }}>Latest benchmark</h3>
              <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", marginBottom: "var(--space-3)" }}>
                {statusBadge(benchmarkQuery.data.items[0].status)}
                <span className="text-muted">
                  {fmtDateTime(benchmarkQuery.data.items[0].completed_at || benchmarkQuery.data.items[0].created_at)}
                </span>
              </div>
              <div className="kv-list">
                {Object.entries(benchmarkQuery.data.items[0].metrics).slice(0, 6).map(([key, value]) => (
                  <div key={key} className="kv-item">
                    <dt>{key.replace(/_/g, " ")}</dt>
                    <dd>{formatMetricValue(value)}</dd>
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
