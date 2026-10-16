/**
 * Client side of the /api/events stream (Server-Sent Events).
 *
 * The API and the MCP server share state only through disk, so the API
 * watches the files and pushes {version, areas} events. This module turns
 * them into scoped React Query refreshes:
 *
 * - the "initial" event sent on every connect is ignored, unless its version
 *   differs from the last one seen (changes missed while disconnected);
 * - an event whose version did not change is ignored;
 * - areas are batched for `throttleMs`, then mapped to the query keys they
 *   affect; "project" resets every query (another project's data must not
 *   linger); an unknown area refreshes everything;
 * - the stream is closed while the tab is hidden and reopened when visible,
 *   so background tabs do not hold one of the browser's ~6 connections per
 *   host (PIPE#4);
 * - a stream the browser gave up on (non-200 answer, wrong content type) is
 *   reopened with backoff. Normal closes (the server ends each stream after
 *   about a minute) are retried by EventSource itself.
 */

export type RefreshPlan = { kind: "reset" } | { kind: "all" } | { kind: "keys"; keys: string[] };

// First element of the query keys each changed area can make stale.
export const AREA_QUERY_KEYS: Record<string, readonly string[]> = {
  // review_state.json blocks other than pipeline/screen/eligibility (search, dedup).
  state: [
    "stats",
    "pipeline-progress",
    "projects",
    "all-papers",
    "search-papers",
    "paper",
    "papers-to-screen",
    "eligibility-papers",
    "report-by-query",
  ],
  pipeline: ["pipeline-progress", "stats"],
  screen: [
    "stats",
    "projects",
    "papers-to-screen",
    "eligibility-papers",
    "all-papers",
    "search-papers",
    "paper",
    "report-by-query",
  ],
  eligibility: ["stats", "projects", "eligibility-papers", "all-papers", "search-papers", "paper"],
  config: ["config", "config-readiness", "report-filter-plan", "report-by-query", "active-project", "projects"],
  downloads: ["download-log"],
};

export function refreshPlan(areas: readonly string[]): RefreshPlan {
  if (areas.includes("project")) return { kind: "reset" };
  if (areas.some((a) => a === "all" || !(a in AREA_QUERY_KEYS))) return { kind: "all" };
  const keys: string[] = [];
  for (const area of areas) {
    for (const key of AREA_QUERY_KEYS[area]) if (!keys.includes(key)) keys.push(key);
  }
  return { kind: "keys", keys };
}

/** The subset of EventSource this module uses (lets tests pass a fake). */
export interface EventSourceLike {
  readyState: number;
  onmessage: ((ev: { data: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onopen: ((ev: unknown) => void) | null;
  close(): void;
}

export interface VisibilitySource {
  hidden: boolean;
  addEventListener(type: "visibilitychange", fn: () => void): void;
  removeEventListener(type: "visibilitychange", fn: () => void): void;
}

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(id: unknown): void;
}

export interface RealtimeOptions {
  url: string;
  onRefresh: (plan: RefreshPlan) => void;
  createEventSource?: (url: string) => EventSourceLike;
  doc?: VisibilitySource;
  timers?: Timers;
  /** Events arriving within this window are merged into one refresh. */
  throttleMs?: number;
  /** First reconnect delay after the browser gave up; doubles up to maxBackoffMs. */
  backoffMs?: number;
  maxBackoffMs?: number;
}

const EVENT_SOURCE_CLOSED = 2;

/** Start syncing; returns a function that stops it. */
export function startRealtimeSync(options: RealtimeOptions): () => void {
  const {
    url,
    onRefresh,
    createEventSource = (u: string) => new EventSource(u) as unknown as EventSourceLike,
    doc = document,
    timers = { setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (id) => clearTimeout(id as number) },
    throttleMs = 1000,
    backoffMs = 2000,
    maxBackoffMs = 30_000,
  } = options;

  let es: EventSourceLike | null = null;
  let lastVersion: string | null = null;
  let messagesOnConnection = 0;
  let pending: string[] = [];
  let flushTimer: unknown = null;
  let reconnectTimer: unknown = null;
  let failures = 0;
  let stopped = false;

  const flush = () => {
    flushTimer = null;
    const areas = pending;
    pending = [];
    if (areas.length) onRefresh(refreshPlan(areas));
  };

  const queue = (areas: readonly string[]) => {
    for (const a of areas) if (!pending.includes(a)) pending.push(a);
    if (flushTimer === null) flushTimer = timers.setTimeout(flush, throttleMs);
  };

  const handle = (raw: string) => {
    failures = 0;
    messagesOnConnection += 1;
    let msg: { version?: unknown; areas?: unknown; initial?: unknown };
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (typeof msg.version !== "string") {
      // API without versions ({"changed": true}): its first event per
      // connection is the sync-on-connect one, anything after is a change.
      if (messagesOnConnection > 1) queue(["all"]);
      return;
    }
    const changed = msg.version !== lastVersion;
    const firstEver = lastVersion === null;
    lastVersion = msg.version;
    if (msg.initial) {
      if (changed && !firstEver) queue(["all"]);
      return;
    }
    if (!changed) return;
    const areas = Array.isArray(msg.areas) ? msg.areas.filter((a): a is string => typeof a === "string") : [];
    queue(areas.length ? areas : ["all"]);
  };

  const disconnect = () => {
    if (reconnectTimer !== null) {
      timers.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (es) {
      es.onopen = null;
      es.onmessage = null;
      es.onerror = null;
      es.close();
      es = null;
    }
  };

  const connect = () => {
    if (stopped || es || doc.hidden) return;
    messagesOnConnection = 0;
    const source = createEventSource(url);
    es = source;
    // Fires again after each automatic reconnect of the same EventSource.
    source.onopen = () => {
      messagesOnConnection = 0;
    };
    source.onmessage = (ev) => handle(ev.data);
    source.onerror = () => {
      // CONNECTING: the browser retries by itself (server closed the stream,
      // network blip). CLOSED: it gave up for good, so retry here.
      if (source.readyState !== EVENT_SOURCE_CLOSED || es !== source) return;
      disconnect();
      const delay = Math.min(maxBackoffMs, backoffMs * 2 ** failures);
      failures += 1;
      reconnectTimer = timers.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };
  };

  const onVisibility = () => {
    if (doc.hidden) disconnect();
    else connect();
  };

  doc.addEventListener("visibilitychange", onVisibility);
  connect();

  return () => {
    stopped = true;
    doc.removeEventListener("visibilitychange", onVisibility);
    disconnect();
    if (flushTimer !== null) {
      timers.clearTimeout(flushTimer);
      flushTimer = null;
    }
  };
}
