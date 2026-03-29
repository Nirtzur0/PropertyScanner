import { Navigate, Route, Routes, Link, useParams } from "react-router-dom";
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

import { TopBar } from "./components/layout/TopBar";
import { ExplorePage } from "./pages/ExplorePage";
import { ListingDetailPage } from "./pages/ListingDetailPage";
import { CompReviewPage } from "./pages/CompReviewPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SystemPage } from "./pages/SystemPage";

class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Uncaught error in React tree:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card" style={{ margin: "2rem auto", maxWidth: 640, textAlign: "center" }}>
          <strong>Something went wrong</strong>
          <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>{this.state.error.message}</p>
          <Link className="btn btn-secondary" to="/" onClick={() => this.setState({ error: null })} style={{ marginTop: "var(--space-3)" }}>
            Back to map
          </Link>
        </div>
      );
    }
    return this.props.children;
  }
}

function CompReviewRedirect() {
  const { listingId } = useParams();
  return <Navigate replace to={`/listings/${listingId}/comps`} />;
}

export default function App() {
  return (
    <div className="app-shell">
      <TopBar />
      <main style={{ padding: "var(--space-4) var(--space-5)" }}>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<ExplorePage />} />
            <Route path="/explore" element={<Navigate replace to="/" />} />
            <Route path="/listings/:listingId" element={<ListingDetailPage />} />
            <Route path="/listings/:listingId/comps" element={<CompReviewPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/system" element={<SystemPage />} />

            {/* Redirects from old routes */}
            <Route path="/workbench" element={<Navigate replace to="/" />} />
            <Route path="/watchlists" element={<Navigate replace to="/library" />} />
            <Route path="/pipeline" element={<Navigate replace to="/system" />} />
            <Route path="/command-center" element={<Navigate replace to="/system" />} />
            <Route path="/comp-reviews/:listingId" element={<CompReviewRedirect />} />
            <Route path="/memos" element={<Navigate replace to="/library?tab=memos" />} />

            <Route
              path="*"
              element={
                <div className="card" style={{ margin: "2rem auto", maxWidth: 640, textAlign: "center" }}>
                  <strong>Page not found</strong>
                  <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>The page you are looking for does not exist.</p>
                  <Link className="btn btn-secondary" to="/" style={{ marginTop: "var(--space-3)", display: "inline-block" }}>Back to map</Link>
                </div>
              }
            />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
