import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { fmtMoney, fmtPct, formatMetricValue } from "../format";
import { track } from "../track";
import type { CompCandidate, CompReviewWorkspaceResponse } from "../types";

function toggleInList(list: string[], id: string, opposing: string[]): string[] {
  if (list.includes(id)) return list.filter((x) => x !== id);
  return [...list.filter((x) => !opposing.includes(x)), id];
}

function Editor({ listingId, data }: { listingId: string; data: CompReviewWorkspaceResponse }) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>(
    data.latest_review?.selected_comp_ids ?? data.pinned_comps.map((c) => c.id),
  );
  const [rejectedIds, setRejectedIds] = useState<string[]>(
    data.latest_review?.rejected_comp_ids ?? data.rejected_comps.map((c) => c.id),
  );
  const [notes, setNotes] = useState(data.latest_review?.notes ?? "");
  const [condAdj, setCondAdj] = useState(String(data.latest_review?.overrides.condition_adjustment_pct ?? ""));
  const [locAdj, setLocAdj] = useState(String(data.latest_review?.overrides.location_adjustment_pct ?? ""));
  const [renAdj, setRenAdj] = useState(String(data.latest_review?.overrides.renovation_adjustment_pct ?? ""));

  const saveReview = useMutation({
    mutationFn: () =>
      api.createCompReview({
        listing_id: listingId,
        status: "draft",
        selected_comp_ids: selectedIds,
        rejected_comp_ids: rejectedIds,
        overrides: {
          ...(condAdj ? { condition_adjustment_pct: Number(condAdj) } : {}),
          ...(locAdj ? { location_adjustment_pct: Number(locAdj) } : {}),
          ...(renAdj ? { renovation_adjustment_pct: Number(renAdj) } : {}),
        },
        notes,
      }),
    onSuccess: async () => {
      track({ event_name: "comp_review_saved", route: `/listings/${listingId}/comps`, subject_type: "listing", subject_id: listingId });
      await queryClient.invalidateQueries({ queryKey: ["comp-review-workspace", listingId] });
    },
  });

  const publishMemo = useMutation({
    mutationFn: () =>
      api.createMemo({
        title: `Comp review memo ${new Date().toISOString().slice(0, 10)}`,
        listing_id: listingId,
        assumptions: ["Comp selection curated in comp workbench."],
        risks: ["Manual adjustments should be reviewed."],
        sections: [{ heading: "Summary", body: `Retained ${selectedIds.length} comps with analyst overrides.` }],
      }),
    onSuccess: () => {
      track({ event_name: "memo_published", route: `/listings/${listingId}/comps`, subject_type: "listing", subject_id: listingId });
      void queryClient.invalidateQueries({ queryKey: ["memos"] });
    },
  });

  function compLabel(c: CompCandidate) {
    if (selectedIds.includes(c.id)) return "Pinned";
    if (rejectedIds.includes(c.id)) return "Rejected";
    if (c.state === "suggested") return "Suggested";
    return "Candidate";
  }

  return (
    <div className="detail-max">
      <div className="breadcrumb">
        <Link to="/">Map</Link>
        <span className="sep" />
        <Link to={`/listings/${listingId}`}>{data.target.title}</Link>
        <span className="sep" />
        <span>Comp Review</span>
      </div>

      <div className="page-header">
        <div className="page-header-info">
          <h1>Comp Review</h1>
          <p>
            {data.target.title} &middot; {fmtMoney(data.target.ask_price)} ask
            {data.baseline_valuation.fair_value != null && ` \u00B7 ${fmtMoney(data.baseline_valuation.fair_value)} baseline`}
          </p>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={() => saveReview.mutate()} disabled={saveReview.isPending || !data.save_review.ready}>
            Save review
          </button>
          <button className="btn btn-secondary" onClick={() => publishMemo.mutate()} disabled={publishMemo.isPending || !data.publish_to_memo.ready}>
            Publish to memo
          </button>
        </div>
      </div>

      <div className="metrics-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Retained median</span>
            <span className="metric-value">{fmtMoney(data.delta_preview.retained_median)}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Shift vs baseline</span>
            <span className="metric-value">{fmtPct(data.delta_preview.baseline_shift_pct)}</span>
          </div>
        </div>
        <div className="card">
          <div className="metric">
            <span className="metric-label">Retained count</span>
            <span className="metric-value">{data.delta_preview.retained_count}</span>
          </div>
        </div>
      </div>

      <div className="two-col">
        {/* Candidate table */}
        <div className="card" style={{ padding: 0 }}>
          <div style={{ padding: "var(--space-4) var(--space-5)" }}>
            <h3>Candidate pool</h3>
          </div>
          <div style={{ overflow: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Comp</th>
                  <th>Distance</th>
                  <th>Size delta</th>
                  <th>Implied value</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.candidate_pool.map((c) => (
                  <tr key={c.id} style={{ cursor: "default" }}>
                    <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{c.title}</td>
                    <td className="mono">{c.distance_km.toFixed(1)} km</td>
                    <td className="mono">{fmtPct(c.size_delta_pct)}</td>
                    <td className="mono">{fmtMoney(c.implied_value)}</td>
                    <td>{compLabel(c)}</td>
                    <td>
                      <div style={{ display: "flex", gap: "var(--space-1)" }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setSelectedIds((cur) => toggleInList(cur, c.id, rejectedIds))}
                        >
                          {selectedIds.includes(c.id) ? "Unpin" : "Pin"}
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setRejectedIds((cur) => toggleInList(cur, c.id, selectedIds))}
                        >
                          {rejectedIds.includes(c.id) ? "Undo" : "Reject"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Adjustments */}
        <div className="card">
          <h3 style={{ marginBottom: "var(--space-4)" }}>Adjustments</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--text-sm)" }}>
              Condition %
              <input type="number" step="0.01" value={condAdj} onChange={(e) => setCondAdj(e.target.value)} placeholder="0.02"
                style={{ height: 32, padding: "0 var(--space-2)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)" }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--text-sm)" }}>
              Location %
              <input type="number" step="0.01" value={locAdj} onChange={(e) => setLocAdj(e.target.value)} placeholder="0.01"
                style={{ height: 32, padding: "0 var(--space-2)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)" }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--text-sm)" }}>
              Renovation %
              <input type="number" step="0.01" value={renAdj} onChange={(e) => setRenAdj(e.target.value)} placeholder="0.03"
                style={{ height: 32, padding: "0 var(--space-2)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)" }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--text-sm)" }}>
              Notes
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4}
                style={{ padding: "var(--space-2)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)", resize: "vertical" }} />
            </label>
          </div>

          {data.adjustment_cards.length > 0 && (
            <>
              <h3 style={{ margin: "var(--space-5) 0 var(--space-3)" }}>Saved adjustments</h3>
              <div className="kv-list">
                {data.adjustment_cards.map((card) => (
                  <div key={card.id} className="kv-item">
                    <dt>{card.label}</dt>
                    <dd>{formatMetricValue(card.value)}</dd>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={{ marginTop: "var(--space-5)", padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-md)", fontSize: "var(--text-sm)" }}>
            <strong>Memo readiness:</strong>{" "}
            {data.publish_to_memo.ready ? "Ready to publish." : data.publish_to_memo.reason}
          </div>
        </div>
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

  if (workspaceQuery.isLoading) {
    return (
      <div className="detail-max">
        <div className="card" style={{ padding: "var(--space-8)", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>Loading comp workbench...</p>
        </div>
      </div>
    );
  }

  if (!workspaceQuery.data) {
    return (
      <div className="detail-max">
        <div className="card" style={{ padding: "var(--space-8)", textAlign: "center" }}>
          <p style={{ color: "var(--accent-danger)" }}>Comp workbench unavailable.</p>
        </div>
      </div>
    );
  }

  const key = [listingId, workspaceQuery.data.latest_review?.id ?? "new", workspaceQuery.data.latest_review?.updated_at ?? ""].join(":");
  return <Editor key={key} listingId={listingId} data={workspaceQuery.data} />;
}
