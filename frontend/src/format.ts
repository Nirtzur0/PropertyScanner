export function fmtMoney(value?: number | null, currency?: string | null) {
  if (value === undefined || value === null) return "N/A";
  const code = currency && /^[A-Z]{3}$/.test(currency) ? currency : "EUR";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${code} ${value.toLocaleString()}`;
  }
}

export function fmtPct(value?: number | null, digits = 1) {
  if (value === undefined || value === null) return "N/A";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtDateTime(value?: string | null) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatMaybeString(value?: string | null, fallback = "N/A") {
  return value && value.trim() ? value : fallback;
}

export function formatMetricValue(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toLocaleString();
    if (Math.abs(value) < 1) return fmtPct(value);
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}
