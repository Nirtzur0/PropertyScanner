const SUCCESS = new Set(["supported", "passed", "success", "completed", "available", "active", "published"]);
const WARNING = new Set(["degraded", "experimental", "running", "draft"]);
const DANGER = new Set(["blocked", "failed"]);

export function statusBadge(status: string) {
  const cls = SUCCESS.has(status)
    ? "badge-success"
    : WARNING.has(status)
      ? "badge-warning"
      : DANGER.has(status)
        ? "badge-danger"
        : "badge-default";
  return <span className={`badge ${cls}`}>{status}</span>;
}
