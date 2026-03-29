import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { formatMaybeString } from "../format";
import { statusBadge } from "../components/StatusBadge";
import type { Memo } from "../types";

type Tab = "watchlists" | "saved-searches" | "memos";

function MemoCard({ memo }: { memo: Memo }) {
  const exportMutation = useMutation({ mutationFn: () => api.exportMemo(memo.id) });
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-2)" }}>
        <strong>{memo.title}</strong>
        {statusBadge(memo.status)}
      </div>
      <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}>
        {memo.sections[0]?.body || "No content yet."}
      </p>
      <button className="btn btn-ghost btn-sm" onClick={() => exportMutation.mutate()}>
        Export
      </button>
      {exportMutation.data && (
        <pre style={{ marginTop: "var(--space-3)", padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-md)", fontSize: "var(--text-xs)", overflow: "auto", maxHeight: 300 }}>
          {exportMutation.data.content}
        </pre>
      )}
    </div>
  );
}

export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab: Tab = rawTab === "saved-searches" || rawTab === "memos" ? rawTab : "watchlists";

  const watchlistsQuery = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists, staleTime: 30_000 });
  const savedSearchesQuery = useQuery({ queryKey: ["saved-searches"], queryFn: api.savedSearches, staleTime: 30_000 });
  const memosQuery = useQuery({ queryKey: ["memos"], queryFn: api.memos, staleTime: 30_000 });

  const TABS: Array<{ id: Tab; label: string; count: number }> = [
    { id: "watchlists", label: "Watchlists", count: watchlistsQuery.data?.total ?? 0 },
    { id: "saved-searches", label: "Saved searches", count: savedSearchesQuery.data?.total ?? 0 },
    { id: "memos", label: "Memos", count: memosQuery.data?.total ?? 0 },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-info">
          <h1>Library</h1>
          <p>Watchlists, saved searches, and memos in one place.</p>
        </div>
        <div className="page-header-actions">
          <Link to="/" className="btn btn-secondary">Back to map</Link>
        </div>
      </div>

      <div className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`tab-btn${tab === t.id ? " is-active" : ""}`}
            onClick={() => setSearchParams({ tab: t.id })}
          >
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {tab === "watchlists" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "var(--space-3)" }}>
          {(watchlistsQuery.data?.items ?? []).length > 0 ? (
            watchlistsQuery.data!.items.map((wl) => (
              <div key={wl.id} className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-2)" }}>
                  <strong>{wl.name}</strong>
                  {statusBadge(wl.status)}
                </div>
                <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}>
                  {formatMaybeString(wl.description, "No description.")}
                </p>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <span className="chip-v2">{wl.listing_ids.length} listings</span>
                  {wl.listing_ids[0] && (
                    <Link to={`/listings/${wl.listing_ids[0]}`} className="btn btn-ghost btn-sm">
                      Open first listing
                    </Link>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state-v2">
              <h3>No watchlists yet</h3>
              <p>Select listings in the Explorer and save them as a watchlist.</p>
            </div>
          )}
        </div>
      )}

      {tab === "saved-searches" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "var(--space-3)" }}>
          {(savedSearchesQuery.data?.items ?? []).length > 0 ? (
            savedSearchesQuery.data!.items.map((ss) => (
              <div key={ss.id} className="card">
                <strong>{ss.name}</strong>
                <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", margin: "var(--space-1) 0" }}>
                  {formatMaybeString(ss.query, "No query saved.")}
                </p>
                <div style={{ display: "flex", gap: "var(--space-1)" }}>
                  <span className="chip-v2">{Object.keys(ss.filters ?? {}).length} filters</span>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state-v2">
              <h3>No saved searches</h3>
              <p>Save a filter configuration from the Explorer.</p>
            </div>
          )}
        </div>
      )}

      {tab === "memos" && (
        <div className="stack-3">
          {(memosQuery.data?.items ?? []).length > 0 ? (
            memosQuery.data!.items.map((memo) => <MemoCard key={memo.id} memo={memo} />)
          ) : (
            <div className="empty-state-v2">
              <h3>No memos</h3>
              <p>Draft a memo from the Explorer or a comp review.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
