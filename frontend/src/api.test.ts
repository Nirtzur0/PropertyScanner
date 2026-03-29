import { describe, it, expect, vi, beforeEach } from "vitest";

// Test the queryString logic by extracting it
// Since queryString is not exported, we test the pattern directly
function queryString(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "" || Number.isNaN(value)) {
      return;
    }
    search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

describe("queryString", () => {
  it("returns empty string for empty params", () => {
    expect(queryString({})).toBe("");
  });

  it("returns empty string when all values are undefined", () => {
    expect(queryString({ a: undefined, b: undefined })).toBe("");
  });

  it("returns empty string when all values are empty strings", () => {
    expect(queryString({ a: "", b: "" })).toBe("");
  });

  it("builds query string from params", () => {
    const result = queryString({ city: "Madrid", limit: 50 });
    expect(result).toContain("city=Madrid");
    expect(result).toContain("limit=50");
    expect(result).toMatch(/^\?/);
  });

  it("skips undefined values", () => {
    const result = queryString({ city: "Madrid", country: undefined });
    expect(result).toContain("city=Madrid");
    expect(result).not.toContain("country");
  });

  it("skips NaN values", () => {
    const result = queryString({ city: "Madrid", price: NaN });
    expect(result).toContain("city=Madrid");
    expect(result).not.toContain("price");
  });

  it("includes zero values", () => {
    const result = queryString({ offset: 0 });
    expect(result).toBe("?offset=0");
  });
});

describe("request error handling", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("throws on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Not Found", { status: 404, statusText: "Not Found" }),
    );

    const { api } = await import("./api");
    await expect(api.health()).rejects.toThrow("Not Found");
  });

  it("throws with response body text on error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"detail":"listing_not_found"}', { status: 404 }),
    );

    const { api } = await import("./api");
    await expect(api.health()).rejects.toThrow("listing_not_found");
  });

  it("resolves on successful response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", app: "test", db_path: "test.db" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { api } = await import("./api");
    const result = await api.health();
    expect(result).toEqual({ status: "ok", app: "test", db_path: "test.db" });
  });
});
