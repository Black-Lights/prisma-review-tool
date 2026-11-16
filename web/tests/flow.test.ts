import { test } from "node:test";
import assert from "node:assert/strict";
import { flowFunnelRows, getFlow, type PrismaFlow } from "../src/lib/flow.ts";
import { buildReportMarkdown, formatCount, mdCell } from "../src/lib/report.ts";

// Synthetic counts that close like the contract requires:
// 5641 - 675 - 4325 - 450 = 191; 191 - 21 = 170; 170 - 120 - 0 = 50.
const FLOW: PrismaFlow = {
  identified: { total: 5641, by_source: { openalex: 3036, scopus: 2605 } },
  removed_before_screening: {
    duplicates: 675,
    automation_ineligible: 4325,
    automation_by_reason: { keyword_rules: 170, required_keywords: 4155 },
  },
  screened: 191,
  screening_excluded: 21,
  awaiting_screening: 450,
  sought_for_retrieval: 170,
  assessed_for_eligibility: 170,
  eligibility_excluded: 120,
  awaiting_eligibility: 0,
  included: 50,
  notes: ["450 records are still marked maybe."],
};

const row = (rows: ReturnType<typeof flowFunnelRows>, key: string) => {
  const found = rows.find((r) => r.key === key);
  assert.ok(found, `row ${key} missing`);
  return found;
};

test("PIPE#12 client: getFlow reads stats.flow and tolerates older or empty stats", () => {
  assert.deepEqual(getFlow({ search: {}, flow: FLOW }), FLOW);
  assert.equal(getFlow({ search: { total: 3 }, screen: {} }), null);
  assert.equal(getFlow({ error: "No pipeline state found. Run the pipeline first." }), null);
  assert.equal(getFlow(undefined), null);
  assert.equal(getFlow({ flow: { identified: {} } }), null);
});

test("PIPE#12 client: every funnel count is the server's flow number", () => {
  const rows = flowFunnelRows(FLOW);
  assert.equal(row(rows, "identified").count, 5641);
  assert.equal(row(rows, "source:openalex").count, 3036);
  assert.equal(row(rows, "source:scopus").count, 2605);
  assert.equal(row(rows, "duplicates").count, 675);
  assert.equal(row(rows, "automation").count, 4325);
  assert.equal(row(rows, "automation:keyword_rules").count, 170);
  assert.equal(row(rows, "automation:required_keywords").count, 4155);
  assert.equal(row(rows, "screened").count, 191);
  assert.equal(row(rows, "screening_excluded").count, 21);
  assert.equal(row(rows, "awaiting_screening").count, 450);
  assert.equal(row(rows, "sought_for_retrieval").count, 170);
  assert.equal(row(rows, "assessed_for_eligibility").count, 170);
  assert.equal(row(rows, "eligibility_excluded").count, 120);
  assert.equal(row(rows, "awaiting_eligibility").count, 0);
  assert.equal(row(rows, "included").count, 50);
});

test("PIPE#12 client: no client-side arithmetic, the numbers are shown as sent", () => {
  const odd = { ...FLOW, screened: 999, included: 7 };
  const rows = flowFunnelRows(odd);
  assert.equal(row(rows, "screened").count, 999);
  assert.equal(row(rows, "included").count, 7);
});

test("WEB#4: human and AI screening exclusions are shown apart when the API splits them", () => {
  const rows = flowFunnelRows({ ...FLOW, screening_excluded_by_method: { manual: 3, ai: 18 } });
  assert.equal(row(rows, "screening_excluded").detail, "human: 3, AI-assisted: 18");
  assert.equal(row(flowFunnelRows(FLOW), "screening_excluded").detail, undefined);
});

test("WEB#4: the gate row comes from the flow even when stats.screen lost its counter", () => {
  const md = buildReportMarkdown({
    projectName: "Alpha review",
    flow: FLOW,
    queryRows: [],
    totalIncluded: 50,
    untaggedScreened: 0,
    filterRows: [],
    plan: null,
    warnings: [],
  });
  assert.match(md, /\| · Required-keyword gate \| 4,155 \|/);
  assert.match(md, /\| · Exclude-keyword rules \| 170 \|/);
  assert.match(md, /\| · Excluded by reviewers at screening \| 21 \|/);
  assert.match(md, /- 450 records are still marked maybe\./);
});

test("WEB#18: Markdown export escapes pipes and formats numbers the same in every locale", () => {
  assert.equal(mdCell("a | b"), "a \\| b");
  assert.equal(mdCell("line\nbreak"), "line break");
  assert.equal(formatCount(5641), "5,641");
  assert.equal(formatCount(undefined), "0");
  const md = buildReportMarkdown({
    projectName: "Pipes | review",
    flow: FLOW,
    queryRows: [
      { name: "q|1", terms: "a OR b", found_raw: 1200, after_dedup: 1000, included: 10, maybe: 5, excluded: 985 },
    ],
    totalIncluded: 50,
    untaggedScreened: 0,
    filterRows: [["Venues / ISSN", "A | B"]],
    plan: { sources: ["openalex"], rows: [{ filter: "open_access", by_source: { openalex: "request" } }] },
    warnings: ["openalex: partial | stopped at 50"],
  });
  assert.match(md, /\| q\\\|1 \| 1,200 \| 1,000 \| 10 \| 5 \| 985 \|/);
  assert.match(md, /\| Venues \/ ISSN \| A \\\| B \|/);
  assert.match(md, /# Search report: Pipes \| review/);
  assert.match(md, /\| open_access \| At source \|/);
});

test("PIPE#12 client: an API without flow counts says so instead of inventing numbers", () => {
  const md = buildReportMarkdown({
    projectName: "Alpha",
    flow: null,
    queryRows: [],
    totalIncluded: 0,
    untaggedScreened: 0,
    filterRows: [],
    plan: null,
    warnings: [],
  });
  assert.match(md, /PRISMA flow counts are not available/);
  assert.doesNotMatch(md, /\| Records screened \|/);
});

test("WEB#8: a settings note is carried into the export", () => {
  const md = buildReportMarkdown({
    projectName: "Alpha",
    flow: FLOW,
    queryRows: [],
    totalIncluded: 50,
    untaggedScreened: 0,
    filterRows: [["Date range", "2020-01-01 to 2024-12-31"]],
    plan: null,
    warnings: [],
    settingsNote: "Settings were edited after the last run.",
  });
  assert.match(md, /_Settings were edited after the last run\._/);
});

test("R-13: records not yet screened are their own row, before and apart from the screened ones", () => {
  const rows = flowFunnelRows({ ...FLOW, included_by_automation: 150 });
  const keys = rows.map((r) => r.key);
  assert.ok(keys.indexOf("awaiting_screening") < keys.indexOf("screened"));
  assert.equal(row(rows, "awaiting_screening").level, 0);
  assert.match(row(rows, "awaiting_screening").label, /not yet screened/i);
  assert.equal(row(rows, "screened").detail, "150 included by keyword rules, no reviewer");
  assert.equal(row(flowFunnelRows(FLOW), "screened").detail, undefined);
});

test("OP-6: the report describes the logged search when there is one, else the settings", async () => {
  const { searchSettings, planFromLog } = await import("../src/lib/report.ts");
  const config = { search: { date_range: { start: "2020-01-01", end: "2026-12-31" }, filters: { venues: ["Nature"] } } };
  const fromSettings = searchSettings(null, config);
  assert.equal(fromSettings.from, "settings");
  assert.deepEqual(fromSettings.rows[0], ["Date range", "2020-01-01 to 2026-12-31"]);

  const log = {
    finished_at: "2026-11-01T10:05:00+00:00",
    tool_version: "1.6.0",
    sources: ["openalex", "semantic_scholar"],
    date_range: { start: "2021-01-01", end: "2025-12-31" },
    max_results_per_query: 500,
    filters: { document_types: ["journal-article"], require_abstract: true, open_access: false, venues: [] },
    truncated: true,
    searches: [
      { source: "openalex", filter_modes: { document_types: "request", require_abstract: "request" } },
      { source: "semantic_scholar", filter_modes: { document_types: "request", require_abstract: "post" } },
    ],
  };
  const fromLog = searchSettings(log, config);
  assert.equal(fromLog.from, "search_log");
  const rows = Object.fromEntries(fromLog.rows);
  assert.equal(rows["Searched"], "2026-11-01 10:05 UTC (tool 1.6.0)");
  assert.equal(rows["Date range"], "2021-01-01 to 2025-12-31");
  assert.equal(rows["Venues / ISSN"], "none");
  assert.equal(rows["Require abstract"], "on");
  assert.ok(rows["Truncated"].startsWith("yes"));
  assert.deepEqual(planFromLog(log), {
    sources: ["openalex", "semantic_scholar"],
    rows: [
      { filter: "document_types", by_source: { openalex: "request", semantic_scholar: "request" } },
      { filter: "require_abstract", by_source: { openalex: "request", semantic_scholar: "post" } },
    ],
  });
  const md = buildReportMarkdown({
    projectName: "Alpha", flow: FLOW, queryRows: [], totalIncluded: 0, untaggedScreened: 0,
    filterRows: fromLog.rows, filterHeading: fromLog.heading, plan: null, warnings: [],
  });
  assert.match(md, /## Search as run \(search log\)/);
  assert.doesNotMatch(md, /current settings/);
});
