import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  ApiError,
  PER_PAGE_OPTIONS,
  fetchAllPapers,
  normalizePerPage,
  normalizeSort,
  updateConfig,
} from "../src/lib/api.ts";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

function mockFetch(status: number, body: unknown, seen: string[] = []) {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    seen.push(String(input));
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return seen;
}

test("WEB#3: a 409 from PUT /api/config surfaces as an ApiError with the structured detail", async () => {
  const detail = { error: "config_changed", message: "changed", current_version: "9-9" };
  mockFetch(409, { detail });
  await assert.rejects(updateConfig({ _version: "1-1" }), (err: unknown) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.status, 409);
    assert.deepEqual(err.detail, detail);
    assert.equal(err.message, "changed");
    return true;
  });
});

test("API errors with a string detail keep it as the message", async () => {
  mockFetch(409, { detail: "The active project marker names a missing project." });
  await assert.rejects(fetchAllPapers(), (err: unknown) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.message, "The active project marker names a missing project.");
    return true;
  });
});

test("WEB#15: the papers query is URL-encoded and an unknown sort column is dropped", async () => {
  const seen = mockFetch(200, { total: 0, page: 1, per_page: 25, total_pages: 0, papers: [] });
  await fetchAllPapers(1, 25, "all", "semantic scholar&x=1", "__class__", "desc");
  const url = new URL(seen[0]);
  assert.equal(url.pathname, "/api/papers");
  assert.equal(url.searchParams.get("source"), "semantic scholar&x=1");
  assert.equal(url.searchParams.get("sort"), null);
  assert.equal(url.searchParams.get("order"), null);
  await fetchAllPapers(2, 50, "include", "all", "year", "desc");
  const url2 = new URL(seen[1]);
  assert.equal(url2.searchParams.get("sort"), "year");
  assert.equal(url2.searchParams.get("order"), "desc");
});

test("WEB#15: saved sort values are whitelisted client-side", () => {
  assert.equal(normalizeSort("year"), "year");
  assert.equal(normalizeSort("title"), "title");
  assert.equal(normalizeSort("year\n"), "");
  assert.equal(normalizeSort("__class__"), "");
  assert.equal(normalizeSort(undefined), "");
});

test("WEB#11: page size is one of the fixed options (the backend allows 1..1000)", () => {
  assert.deepEqual([...PER_PAGE_OPTIONS], [25, 50, 100, 250, 500, 1000]);
  assert.equal(normalizePerPage(100), 100);
  assert.equal(normalizePerPage("250"), 250);
  assert.equal(normalizePerPage(37), 50);
  assert.equal(normalizePerPage(5000), 1000);
  assert.equal(normalizePerPage("abc"), 25);
});
