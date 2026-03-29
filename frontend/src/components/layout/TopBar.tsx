import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

const NAV_ITEMS = [
  { to: "/", label: "Map" },
  { to: "/library", label: "Library" },
  { to: "/system", label: "System" },
] as const;

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: ok ? "var(--accent-success)" : "var(--accent-warning)",
        display: "inline-block",
      }}
    />
  );
}

export function TopBar() {
  const pipelineQuery = useQuery({
    queryKey: ["pipeline"],
    queryFn: api.pipeline,
    staleTime: 15_000,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    staleTime: 15_000,
  });

  const needsRefresh = Boolean(pipelineQuery.data?.needs_refresh);
  const runningJobs = (jobsQuery.data?.items ?? []).filter(
    (j) => String(j.status ?? "").toLowerCase() === "running",
  ).length;

  return (
    <header className="topbar">
      <div className="topbar-left">
        <NavLink to="/" className="topbar-brand">
          <div className="topbar-logo" />
          <span className="topbar-title">Property Scanner</span>
        </NavLink>
        <nav className="topbar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `topbar-nav-link${isActive ? " is-active" : ""}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="topbar-right">
        <span className="topbar-status">
          <StatusDot ok={!needsRefresh} />
          {needsRefresh ? "Needs refresh" : "Fresh"}
        </span>
        <span className="topbar-status">
          <StatusDot ok={runningJobs === 0} />
          {runningJobs} jobs
        </span>
      </div>
    </header>
  );
}
