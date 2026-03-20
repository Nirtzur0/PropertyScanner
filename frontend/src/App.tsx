import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "./api";
import {
  CompReviewPage,
  DecisionsPage,
  ListingPage,
  PipelinePage,
  WorkbenchPage,
} from "./pages";
import { track } from "./track";
import "./styles.css";

const NAV_ITEMS = [
  { to: "/workbench", label: "Workbench" },
  { to: "/watchlists", label: "Decisions" },
  { to: "/pipeline", label: "Pipeline" },
] as const;

function CommandCenterRedirect() {
  useEffect(() => {
    track({
      event_name: "command_center_redirected",
      route: "/command-center",
      subject_type: "route",
      subject_id: "pipeline",
      context: { destination: "/pipeline" },
    });
  }, []);

  return <Navigate replace to="/pipeline" />;
}

function AppChrome() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 30_000,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    staleTime: 15_000,
  });
  const pipelineQuery = useQuery({
    queryKey: ["pipeline"],
    queryFn: api.pipeline,
    staleTime: 15_000,
  });

  const pendingJobs = (jobsQuery.data?.items ?? []).filter(
    (job) => String(job.status ?? "").toLowerCase() === "running",
  ).length;
  const failedJobs = (jobsQuery.data?.items ?? []).filter(
    (job) => String(job.status ?? "").toLowerCase() === "failed",
  ).length;
  const needsRefresh = Boolean(pipelineQuery.data?.needs_refresh);

  return (
    <div className="app-shell">
      <header className="chrome-header">
        <div className="brand-lockup">
          <div className="brand-mark" />
          <div>
            <p className="eyebrow">Local-first analyst platform</p>
            <h1>Property Scanner</h1>
          </div>
        </div>
        <nav className="global-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => `global-nav-link${isActive ? " is-active" : ""}`}
              to={item.to}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="status-tray">
          <div className="status-card">
            <span className="tray-label">API</span>
            <strong>{String(healthQuery.data?.status ?? "loading")}</strong>
          </div>
          <div className="status-card">
            <span className="tray-label">Jobs</span>
            <strong>{pendingJobs}</strong>
            <p>{failedJobs} failed</p>
          </div>
          <div className={`status-card${needsRefresh ? " is-warn" : ""}`}>
            <span className="tray-label">Pipeline</span>
            <strong>{needsRefresh ? "Refresh" : "Fresh"}</strong>
          </div>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<Navigate replace to="/workbench" />} />
        <Route path="/workbench" element={<WorkbenchPage />} />
        <Route path="/listings/:listingId" element={<ListingPage />} />
        <Route path="/comp-reviews/:listingId" element={<CompReviewPage />} />
        <Route path="/memos" element={<Navigate replace to="/watchlists?tab=memos" />} />
        <Route path="/watchlists" element={<DecisionsPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/command-center" element={<CommandCenterRedirect />} />
      </Routes>
    </div>
  );
}

export default AppChrome;
