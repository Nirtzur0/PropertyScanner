import { describe, it, expect } from "vitest";
import { fmtMoney, fmtPct, fmtDateTime, formatMaybeString, formatMetricValue } from "./format";

describe("fmtMoney", () => {
  it("returns N/A for null", () => {
    expect(fmtMoney(null)).toBe("N/A");
  });

  it("returns N/A for undefined", () => {
    expect(fmtMoney(undefined)).toBe("N/A");
  });

  it("formats EUR by default", () => {
    const result = fmtMoney(250000);
    expect(result).toContain("250,000");
  });

  it("uses provided currency code", () => {
    const result = fmtMoney(100000, "GBP");
    expect(result).toContain("100,000");
    expect(result).toMatch(/£|GBP/);
  });

  it("falls back to EUR for invalid currency code", () => {
    const result = fmtMoney(50000, "invalid");
    expect(result).toContain("50,000");
  });

  it("falls back to EUR for lowercase currency", () => {
    const result = fmtMoney(50000, "eur");
    // lowercase doesn't match /^[A-Z]{3}$/, so falls back to EUR
    expect(result).toContain("50,000");
  });

  it("handles zero", () => {
    const result = fmtMoney(0);
    expect(result).not.toBe("N/A");
  });

  it("handles negative values", () => {
    const result = fmtMoney(-10000);
    expect(result).toContain("10,000");
  });
});

describe("fmtPct", () => {
  it("returns N/A for null", () => {
    expect(fmtPct(null)).toBe("N/A");
  });

  it("returns N/A for undefined", () => {
    expect(fmtPct(undefined)).toBe("N/A");
  });

  it("formats decimal as percentage", () => {
    expect(fmtPct(0.05)).toBe("5.0%");
  });

  it("formats with custom digits", () => {
    expect(fmtPct(0.123, 2)).toBe("12.30%");
  });

  it("handles zero", () => {
    expect(fmtPct(0)).toBe("0.0%");
  });

  it("handles 100%", () => {
    expect(fmtPct(1.0)).toBe("100.0%");
  });

  it("handles negative percentages", () => {
    expect(fmtPct(-0.15)).toBe("-15.0%");
  });
});

describe("fmtDateTime", () => {
  it("returns 'No timestamp' for null", () => {
    expect(fmtDateTime(null)).toBe("No timestamp");
  });

  it("returns 'No timestamp' for empty string", () => {
    expect(fmtDateTime("")).toBe("No timestamp");
  });

  it("returns raw value for invalid date string", () => {
    expect(fmtDateTime("not-a-date")).toBe("not-a-date");
  });

  it("formats valid ISO date", () => {
    const result = fmtDateTime("2025-01-15T10:30:00Z");
    expect(result).not.toBe("No timestamp");
    expect(result).not.toBe("2025-01-15T10:30:00Z");
  });
});

describe("formatMaybeString", () => {
  it("returns fallback for null", () => {
    expect(formatMaybeString(null)).toBe("N/A");
  });

  it("returns fallback for undefined", () => {
    expect(formatMaybeString(undefined)).toBe("N/A");
  });

  it("returns fallback for empty string", () => {
    expect(formatMaybeString("")).toBe("N/A");
  });

  it("returns fallback for whitespace-only string", () => {
    expect(formatMaybeString("   ")).toBe("N/A");
  });

  it("returns value for non-empty string", () => {
    expect(formatMaybeString("hello")).toBe("hello");
  });

  it("uses custom fallback", () => {
    expect(formatMaybeString(null, "Unknown")).toBe("Unknown");
  });
});

describe("formatMetricValue", () => {
  it("returns N/A for null", () => {
    expect(formatMetricValue(null)).toBe("N/A");
  });

  it("returns N/A for undefined", () => {
    expect(formatMetricValue(undefined)).toBe("N/A");
  });

  it("formats integer without decimal points", () => {
    const result = formatMetricValue(42);
    expect(result).toBe("42");
  });

  it("formats large integers with commas", () => {
    const result = formatMetricValue(1000000);
    expect(result).toContain("1,000,000");
  });

  it("formats small decimals as percentages", () => {
    expect(formatMetricValue(0.05)).toBe("5.0%");
  });

  it("formats larger decimals with 2 decimal places", () => {
    const result = formatMetricValue(3.14159);
    expect(result).toContain("3.14");
  });

  it("formats booleans as Yes/No", () => {
    expect(formatMetricValue(true)).toBe("Yes");
    expect(formatMetricValue(false)).toBe("No");
  });

  it("formats strings as-is", () => {
    expect(formatMetricValue("active")).toBe("active");
  });

  it("does not treat integers as percentages", () => {
    // Regression: integers were previously treated as percentages
    expect(formatMetricValue(5)).toBe("5");
    expect(formatMetricValue(100)).toBe("100");
  });
});
