/**
 * Markdown for "Export search report". Pure so the export is testable and
 * identical in every browser locale (WEB#18).
 */
import type { FilterMode, QueryReportRow } from "./api";
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

export interface ReportInput {
  projectName: string;
  flow: PrismaFlow | null;
  queryRows: QueryReportRow[];
  totalIncluded: number;
  untaggedScreened: number;
  filterRows: [string, string][];
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

  L.push("", "## Source filters (current settings)", "", "| Filter | Value |", "| --- | --- |");
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
