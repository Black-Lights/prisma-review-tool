/**
 * Markdown for "Export search report". Pure so the export is testable and
 * identical in every browser locale (WEB#18).
 */
import type { ConfigData, FilterMode, QueryReportRow, SearchLog } from "./api";
import { flowFunnelRows, type PrismaFlow } from "./flow.ts";

export const FILTER_MODE_LABEL: Record<FilterMode, string> = {
  request: "At source",
  post: "After call",
  unsupported: "Ignored",
};

/** Counts in exported text use one fixed grouping style, whatever the browser locale. */
export function formatCount(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("en-US") : "0";
}

/** A Markdown table cell: pipes escaped, line breaks flattened. */
export function mdCell(value: unknown): string {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\|/g, "\\|");
}

function valueOf(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
  if (typeof v === "boolean") return v ? "on" : "off";
  return v ? String(v) : "none";
}

/** "2026-06-21 13:04 UTC", the same in every browser locale. */
export function utcMinute(iso: string | null | undefined): string {
  const t = Date.parse(iso ?? "");
  return Number.isNaN(t) ? "unknown time" : `${new Date(t).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** The search settings the report describes, and where they come from. */
export interface SearchSettings {
  /** "search_log": the last completed search as it ran; "settings": the current config. */
  from: "search_log" | "settings";
  heading: string;
  rows: [string, string][];
}

/**
 * The search part of the report: from the search log of the last completed
 * search when there is one (so the report describes the search that produced
 * the counts, whatever the settings say now), else from the current settings.
 */
export function searchSettings(log: SearchLog | null | undefined, config: ConfigData | undefined): SearchSettings {
  if (log) {
    const f = log.filters ?? {};
    const range = log.date_range ?? {};
    const rows: [string, string][] = [
      ["Searched", `${utcMinute(log.finished_at)}${log.tool_version ? ` (tool ${log.tool_version})` : ""}`],
      ["Sources", valueOf(log.sources)],
      ["Date range", `${range.start || "?"} to ${range.end || "?"}`],
      ["Max results per query", valueOf(log.max_results_per_query)],
      ["Document types", valueOf(f.document_types)],
      ["Require abstract", valueOf(f.require_abstract ?? false)],
      ["Open access", valueOf(f.open_access ?? false)],
      ["Venues / ISSN", valueOf(f.venues)],
    ];
    if (log.truncated) rows.push(["Truncated", "yes: some searches matched more than max results per query"]);
    return { from: "search_log", heading: "Search as run (search log)", rows };
  }
  const filters = config?.search?.filters ?? {};
  const range = config?.search?.date_range ?? {};
  return {
    from: "settings",
    heading: "Source filters (current settings)",
    rows: [
      ["Date range", `${range.start || "?"} to ${range.end || "?"}`],
      ["Document types", valueOf(filters.document_types)],
      ["Require abstract", valueOf(filters.require_abstract ?? false)],
      ["Open access", valueOf(filters.open_access ?? false)],
      ["Venues / ISSN", valueOf(filters.venues)],
    ],
  };
}

export interface ReportInput {
  projectName: string;
  flow: PrismaFlow | null;
  queryRows: QueryReportRow[];
  totalIncluded: number;
  untaggedScreened: number;
  filterRows: [string, string][];
  /** Heading of the filter table (default: current settings). */
  filterHeading?: string;
  plan: { sources: string[]; rows: { filter: string; by_source: Record<string, FilterMode> }[] } | null;
  warnings: string[];
  /** Shown under the filter table when the settings changed after the last run. */
  settingsNote?: string | null;
}

export function buildReportMarkdown(input: ReportInput): string {
  const { flow, queryRows, plan, warnings } = input;
  const L: string[] = [];
  L.push(`# Search report: ${input.projectName.replace(/\r?\n/g, " ")}`, "");

  L.push("## PRISMA flow", "");
  if (flow) {
    L.push("| Stage | Count |", "| --- | ---: |");
    for (const row of flowFunnelRows(flow)) {
      const detail = row.detail ? ` (${mdCell(row.detail)})` : "";
      L.push(`| ${row.level ? "· " : ""}${mdCell(row.label)}${detail} | ${formatCount(row.count)} |`);
    }
    if (flow.notes?.length) {
      L.push("");
      flow.notes.forEach((note) => L.push(`- ${note.replace(/\r?\n/g, " ")}`));
    }
  } else {
    L.push("_PRISMA flow counts are not available from this API version. Update the tool and reload._");
  }

  if (queryRows.length) {
    L.push("", "## Results per query (with overlap, queries are OR'd)", "");
    L.push("| Query | Found (raw) | After dedup | Included | Maybe | Excluded |");
    L.push("| --- | ---: | ---: | ---: | ---: | ---: |");
    queryRows.forEach((q) =>
      L.push(
        `| ${mdCell(q.name)} | ${formatCount(q.found_raw)} | ${formatCount(q.after_dedup)} | ${formatCount(q.included)} | ${formatCount(q.maybe)} | ${formatCount(q.excluded)} |`,
      ),
    );
    L.push(
      "",
      `_A paper matched by several queries is counted under each, so column sums exceed the ${formatCount(input.totalIncluded)} distinct included._`,
    );
    if (input.untaggedScreened > 0) {
      L.push(
        `_${formatCount(input.untaggedScreened)} screened paper(s) carry no query tag (searched before per-query tracking); re-run the search to attribute them._`,
      );
    }
  }

  L.push("", `## ${input.filterHeading ?? "Source filters (current settings)"}`, "", "| Filter | Value |", "| --- | --- |");
  input.filterRows.forEach(([k, v]) => L.push(`| ${mdCell(k)} | ${mdCell(v)} |`));
  if (input.settingsNote) L.push("", `_${input.settingsNote}_`);

  if (plan && plan.rows.length) {
    L.push("", "## Where each filter is applied", "");
    L.push(`| Filter | ${plan.sources.map(mdCell).join(" | ")} |`);
    L.push(`| --- | ${plan.sources.map(() => "---").join(" | ")} |`);
    plan.rows.forEach((row) =>
      L.push(
        `| ${mdCell(row.filter)} | ${plan.sources.map((s) => FILTER_MODE_LABEL[row.by_source[s] ?? "unsupported"]).join(" | ")} |`,
      ),
    );
    L.push(
      "",
      "_At source = sent in the request (server-side). After call = enforced locally after fetch. Ignored = source can't express it._",
    );
  }

  if (warnings.length) {
    L.push("", "## Transparency warnings (last run)", "");
    warnings.forEach((w) => L.push(`- ${w.replace(/\r?\n/g, " ")}`));
  }
  return L.join("\n");
}

// Labels of the backend's filter keys (prisma_review/search/filters.py, _LABELS).
const FILTER_LABEL: Record<string, string> = {
  document_types: "document_types",
  require_abstract: "require_abstract",
  open_access: "open_access",
  venues_issn: "venues (ISSN)",
  venues_name: "venues (name)",
};

/** Where each filter was applied in the logged search, per source (same shape as /api/reports/filter-plan). */
export function planFromLog(
  log: SearchLog,
): { sources: string[]; rows: { filter: string; by_source: Record<string, FilterMode> }[] } {
  const sources = log.sources ?? [];
  const searches = (log.searches ?? []) as { source?: string; filter_modes?: Record<string, FilterMode> }[];
  const keys: string[] = [];
  for (const s of searches) for (const k of Object.keys(s.filter_modes ?? {})) if (!keys.includes(k)) keys.push(k);
  const modesOf = (source: string) => searches.find((s) => s.source === source)?.filter_modes ?? {};
  return {
    sources,
    rows: keys.map((k) => ({
      filter: FILTER_LABEL[k] ?? k,
      by_source: Object.fromEntries(sources.map((src) => [src, modesOf(src)[k] ?? "unsupported"])),
    })),
  };
}
