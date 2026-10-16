import { test } from "node:test";
import assert from "node:assert/strict";
import {
  AREA_QUERY_KEYS,
  refreshPlan,
  startRealtimeSync,
  type EventSourceLike,
  type RefreshPlan,
} from "../src/lib/realtime.ts";

const CONNECTING = 0;
const OPEN = 1;
const CLOSED = 2;

class FakeEventSource implements EventSourceLike {
  readyState = CONNECTING;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onopen: ((ev: unknown) => void) | null = null;
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
  }
  close() {
    this.closed = true;
    this.readyState = CLOSED;
  }
  emit(data: object) {
    this.readyState = OPEN;
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  fail(state: number) {
    this.readyState = state;
    this.onerror?.({});
  }
}

class FakeDocument {
  hidden = false;
  private listeners: (() => void)[] = [];
  addEventListener(_type: "visibilitychange", fn: () => void) {
    this.listeners.push(fn);
  }
  removeEventListener(_type: "visibilitychange", fn: () => void) {
    this.listeners = this.listeners.filter((l) => l !== fn);
  }
  setHidden(hidden: boolean) {
    this.hidden = hidden;
    this.listeners.forEach((l) => l());
  }
  get listenerCount() {
    return this.listeners.length;
  }
}

class FakeTimers {
  now = 0;
  private next = 1;
  private timers = new Map<number, { at: number; fn: () => void }>();
  setTimeout = (fn: () => void, ms: number) => {
    const id = this.next++;
    this.timers.set(id, { at: this.now + ms, fn });
    return id;
  };
  clearTimeout = (id: unknown) => {
    this.timers.delete(id as number);
  };
  advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = [...this.timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at);
      if (!due.length) break;
      const [id, t] = due[0];
      this.timers.delete(id);
      this.now = t.at;
      t.fn();
    }
    this.now = end;
  }
  get pending() {
    return this.timers.size;
  }
}

function setup(hidden = false) {
  const sources: FakeEventSource[] = [];
  const plans: RefreshPlan[] = [];
  const doc = new FakeDocument();
  doc.hidden = hidden;
  const timers = new FakeTimers();
  const stop = startRealtimeSync({
    url: "http://api/events",
    onRefresh: (plan) => plans.push(plan),
    createEventSource: (url) => {
      const es = new FakeEventSource(url);
      sources.push(es);
      return es;
    },
    doc,
    timers,
    throttleMs: 1000,
  });
  return { sources, plans, doc, timers, stop, last: () => sources[sources.length - 1] };
}

test("PIPE#14: the initial event on first connect is ignored (queries were just fetched)", () => {
  const { last, plans, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  timers.advance(5000);
  assert.deepEqual(plans, []);
});

test("PIPE#14: an unchanged version is ignored, a changed one invalidates only its areas", () => {
  const { last, plans, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  last().emit({ version: "v1", areas: ["screen"] });
  timers.advance(2000);
  assert.deepEqual(plans, []);
  last().emit({ version: "v2", areas: ["downloads"] });
  timers.advance(2000);
  assert.deepEqual(plans, [{ kind: "keys", keys: ["download-log"] }]);
});

test("PIPE#14: a burst of events is batched into one refresh after the throttle window", () => {
  const { last, plans, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  last().emit({ version: "v2", areas: ["downloads"] });
  timers.advance(300);
  last().emit({ version: "v3", areas: ["config"] });
  timers.advance(300);
  assert.equal(plans.length, 0);
  timers.advance(1000);
  assert.equal(plans.length, 1);
  const plan = plans[0];
  assert.equal(plan.kind, "keys");
  if (plan.kind === "keys") {
    assert.ok(plan.keys.includes("download-log"));
    assert.ok(plan.keys.includes("config"));
    assert.ok(!plan.keys.includes("papers-to-screen"));
  }
});

test("PIPE#14: a project change resets every query", () => {
  const { last, plans, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  last().emit({ version: "v2", areas: ["state", "project"] });
  timers.advance(1500);
  assert.deepEqual(plans, [{ kind: "reset" }]);
});

test("PIPE#4 / WEB#2: the stream is closed while the tab is hidden and reopened when visible", () => {
  const { sources, doc, last } = setup();
  assert.equal(sources.length, 1);
  last().emit({ version: "v1", areas: ["all"], initial: true });
  doc.setHidden(true);
  assert.ok(sources[0].closed, "hidden tab still holds a connection");
  doc.setHidden(false);
  assert.equal(sources.length, 2);
  assert.ok(!sources[1].closed);
});

test("PIPE#4: a tab opened in the background connects only once it becomes visible", () => {
  const { sources, doc } = setup(true);
  assert.equal(sources.length, 0);
  doc.setHidden(false);
  assert.equal(sources.length, 1);
});

test("PIPE#14: changes missed while hidden are caught up by the next initial event", () => {
  const { last, doc, plans, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  doc.setHidden(true);
  doc.setHidden(false);
  last().emit({ version: "v1", areas: ["all"], initial: true });
  timers.advance(2000);
  assert.deepEqual(plans, [], "same version after reconnect: nothing to do");
  doc.setHidden(true);
  doc.setHidden(false);
  last().emit({ version: "v9", areas: ["all"], initial: true });
  timers.advance(2000);
  assert.deepEqual(plans, [{ kind: "all" }]);
});

test("WEB#14: a stream the browser gave up on (non-200, wrong type) is reopened with backoff", () => {
  const { sources, last, timers } = setup();
  last().fail(CLOSED);
  assert.equal(sources.length, 1);
  timers.advance(1999);
  assert.equal(sources.length, 1);
  timers.advance(1);
  assert.equal(sources.length, 2, "no reconnect after a permanent error");
  last().fail(CLOSED);
  timers.advance(3999);
  assert.equal(sources.length, 2);
  timers.advance(1);
  assert.equal(sources.length, 3, "backoff doubles");
});

test("WEB#5 client: the server closing a stream (browser reconnecting by itself) needs no action", () => {
  const { sources, last, timers } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  last().fail(CONNECTING);
  timers.advance(60_000);
  assert.equal(sources.length, 1);
  assert.ok(!sources[0].closed);
});

test("WEB#14: older API without versions still refreshes, skipping its sync-on-connect event", () => {
  const { last, plans, timers } = setup();
  last().emit({ changed: true });
  timers.advance(2000);
  assert.deepEqual(plans, []);
  last().emit({ changed: true });
  timers.advance(2000);
  assert.deepEqual(plans, [{ kind: "all" }]);
});

test("stop() closes the stream, cancels timers and removes the visibility listener", () => {
  const { last, doc, timers, stop } = setup();
  last().emit({ version: "v1", areas: ["all"], initial: true });
  last().emit({ version: "v2", areas: ["screen"] });
  stop();
  assert.ok(last().closed);
  assert.equal(timers.pending, 0);
  assert.equal(doc.listenerCount, 0);
});

test("refreshPlan maps areas to query keys; unknown areas refresh everything", () => {
  assert.deepEqual(refreshPlan(["project"]), { kind: "reset" });
  assert.deepEqual(refreshPlan(["all"]), { kind: "all" });
  assert.deepEqual(refreshPlan(["something-new"]), { kind: "all" });
  assert.deepEqual(refreshPlan([]), { kind: "keys", keys: [] });
  const plan = refreshPlan(["config"]);
  assert.equal(plan.kind, "keys");
  if (plan.kind === "keys") assert.deepEqual(plan.keys, [...AREA_QUERY_KEYS.config]);
  for (const area of ["state", "pipeline", "screen", "eligibility", "config", "downloads"]) {
    assert.ok(area in AREA_QUERY_KEYS, `contract area ${area} has no mapping`);
  }
});
