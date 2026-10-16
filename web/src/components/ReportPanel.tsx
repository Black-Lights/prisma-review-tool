"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Download, AlertTriangle, Layers } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import {
  fetchStats,
  fetchConfig,
  fetchPipelineProgress,
  fetchReportByQuery,
  fetchFilterPlan,
  type FilterMode,
} from "@/lib/api";
import { configEditedSince } from "@/lib/configForm";
import { flowFunnelRows, getFlow, type FunnelRow } from "@/lib/flow";
import { FILTER_MODE_LABEL, buildReportMarkdown, formatCount } from "@/lib/report";

/**
 * Read-only pipeline report: what came in, what was filtered, and how.
 * Counts come only from the PRISMA flow computed by the API (stats.flow), so
 * they match the diagram and the exported reports. Filters and the filter plan
 * describe the current settings, which can differ from the last run.
 */
export default function ReportPanel() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: fetchStats, staleTime: 30_000 });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig, staleTime: 30_000 });
  const { data: progress } = useQuery({
    queryKey: ["pipeline-progress"],
    queryFn: fetchPipelineProgress,
    staleTime: 30_000,
  });
  const { data: byQuery } = useQuery({
    queryKey: ["report-by-query"],
    queryFn: fetchReportByQuery,
    staleTime: 30_000,
  });
  const { data: filterPlan } = useQuery({
    queryKey: ["report-filter-plan"],
    queryFn: fetchFilterPlan,
    staleTime: 30_000,
  });

  const flow = getFlow(stats);
  const hasSearch = !!stats && !stats.error && Object.keys(stats.search ?? {}).length > 0;
  const hasData = flow !== null || hasSearch;
  const funnel = flow ? flowFunnelRows(flow) : [];

  const filters = config?.search?.filters ?? {};
  const dateRange = config?.search?.date_range ?? {};
  const warnings: string[] = progress?.warnings ?? [];

  const queryRows = byQuery?.queries ?? [];
  const untaggedScreened = byQuery?.untagged?.screened ?? 0;
  const hasQueryData = queryRows.length > 0;
  const totalIncluded = byQuery?.total_included ?? flow?.sought_for_retrieval ?? 0;

  const planSources = filterPlan?.sources ?? [];
  const planRows = filterPlan?.filters ?? [];
  const hasPlanData = !filterPlan?.empty && planRows.length > 0;

  // The settings below are the current ones; flag when they were saved after
  // the last pipeline run started, so nobody documents filters never applied.
  const settingsNote = configEditedSince(config?._version, progress?.started_at)
    ? `Settings were saved after the last pipeline run started (${utcMinute(progress?.started_at)}). ` +
      "The filters below are the current settings and may not be the ones that produced these counts. Re-run the pipeline to align them."
    : null;

  // request = filtered at the source; post = filtered locally after the call;
  // unsupported = the source can't express it, so it's ignored there.
  const modeClass: Record<FilterMode, string> = {
    request: "text-accent-green",
    post: "text-accent-amber",
    unsupported: "text-text-muted",
  };

  const valueOf = (v: unknown): string => {
    if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
    if (typeof v === "boolean") return v ? "on" : "off";
    return v ? String(v) : "none";
  };

  const filterRows: [string, string][] = [
    ["Date range", `${dateRange.start || "?"} to ${dateRange.end || "?"}`],
    ["Document types", valueOf(filters.document_types)],
    ["Require abstract", valueOf(filters.require_abstract ?? false)],
    ["Open access", valueOf(filters.open_access ?? false)],
    ["Venues / ISSN", valueOf(filters.venues)],
  ];

  const handleExport = () => {
    const md = buildReportMarkdown({
      projectName: config?.project?.name ?? "PRISMA Review",
      flow,
      queryRows,
      totalIncluded,
      untaggedScreened,
      filterRows,
      plan: hasPlanData ? { sources: planSources, rows: planRows } : null,
      warnings,
      settingsNote,
    });
    const project = (config?.project?.name ?? "report").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `search-report-${project}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <GlassCard data-tutorial="report-panel" className="!p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClipboardList size={18} className="text-primary" />
          <span className="text-sm font-semibold text-text-primary">Pipeline report</span>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={!hasData}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-primary/15 text-primary border border-primary/20 hover:bg-primary/25 disabled:opacity-40 transition-colors cursor-pointer"
        >
          <Download size={14} />
          Export search report
        </button>
      </div>

      {!hasData ? (
        <p className="text-sm text-text-muted">
          No pipeline data yet. Run a search to populate the report.
        </p>
      ) : (
        <div className="space-y-6">
          {/* 1) PRISMA flow */}
          <section>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2">
              PRISMA flow: what came in, what was removed, what is left
            </h3>
            {flow ? (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-text-muted">
                        <th className="font-medium py-1.5 px-2 border-b border-border-glass">Stage</th>
                        <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {funnel.map((row) => (
                        <Row key={row.key} row={row} />
                      ))}
                    </tbody>
                  </table>
                </div>
                {flow.notes.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {flow.notes.map((note, i) => (
                      <li key={i} className="text-xs text-text-muted leading-relaxed">
                        {note}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-xs text-accent-amber">
                PRISMA flow counts are not available from this API version. Update the tool and reload.
              </p>
            )}
          </section>

          {/* 1.5) Results per query */}
          {hasQueryData && (
            <section>
              <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2 flex items-center gap-1.5">
                <Layers size={13} className="text-primary" />
                Results per query: how many of each query reached each stage
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-text-muted">
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass">Query</th>
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Found</th>
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">After dedup</th>
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Included</th>
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Maybe</th>
                      <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Excluded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queryRows.map((q, i) => (
                      <tr key={`${q.name}-${i}`}>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-text-secondary font-mono text-xs" title={q.terms}>
                          {q.name}
                        </td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-text-muted">{formatCount(q.found_raw)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-text-primary">{formatCount(q.after_dedup)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-green">{formatCount(q.included)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-amber">{formatCount(q.maybe)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-red">{formatCount(q.excluded)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-text-muted mt-2">
                A paper matched by several queries is counted under each (queries are OR&apos;d), so the columns
                sum to more than the {formatCount(totalIncluded)} distinct included.
                {untaggedScreened > 0 && (
                  <>
                    {" "}
                    <span className="text-accent-amber">
                      {formatCount(untaggedScreened)} paper(s) have no query tag (searched before per-query
                      tracking): re-run the search to attribute them.
                    </span>
                  </>
                )}
              </p>
            </section>
          )}

          {/* 2) Source filters */}
          <section>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2">
              Source filters (current settings): how the request is narrowed
            </h3>
            {settingsNote && (
              <p className="text-xs text-accent-amber mb-2 flex items-start gap-1.5">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                {settingsNote}
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-muted">
                    <th className="font-medium py-1.5 px-2 border-b border-border-glass">Filter</th>
                    <th className="font-medium py-1.5 px-2 border-b border-border-glass">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {filterRows.map(([k, v]) => (
                    <tr key={k}>
                      <td className="py-1.5 px-2 border-b border-border-glass/40 text-text-secondary">{k}</td>
                      <td className="py-1.5 px-2 border-b border-border-glass/40 text-text-primary font-mono text-xs">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasPlanData ? (
              <div className="mt-4">
                <h4 className="text-xs text-text-secondary mb-2">
                  Where each filter is applied: at the source vs. after the call
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-text-muted">
                        <th className="font-medium py-1.5 px-2 border-b border-border-glass">Filter</th>
                        {planSources.map((s) => (
                          <th key={s} className="font-medium py-1.5 px-2 border-b border-border-glass">{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {planRows.map((row) => (
                        <tr key={row.filter}>
                          <td className="py-1.5 px-2 border-b border-border-glass/40 text-text-secondary">{row.filter}</td>
                          {planSources.map((s) => {
                            const mode = (row.by_source[s] ?? "unsupported") as FilterMode;
                            return (
                              <td key={s} className={`py-1.5 px-2 border-b border-border-glass/40 text-xs ${modeClass[mode]}`}>
                                {FILTER_MODE_LABEL[mode]}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-text-muted mt-2">
                  <span className="text-accent-green">At source</span> = sent in the request and filtered server-side.{" "}
                  <span className="text-accent-amber">After call</span> = the source can&apos;t express it, so it&apos;s enforced
                  locally on the returned records.{" "}
                  <span className="text-text-muted">Ignored</span> = unsupported by that source.
                </p>
              </div>
            ) : (
              <p className="text-xs text-text-muted mt-2">
                No active source filters. See &quot;Transparency warnings&quot; below for query-degradation notes.
              </p>
            )}
          </section>

          {/* 3) Transparency warnings */}
          {warnings.length > 0 && (
            <section>
              <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2 flex items-center gap-1.5">
                <AlertTriangle size={13} className="text-accent-amber" />
                Transparency warnings (last run)
              </h3>
              <ul className="space-y-1.5">
                {warnings.map((w, i) => (
                  <li key={i} className="text-xs text-text-secondary leading-relaxed pl-3 border-l-2 border-accent-amber/30">
                    {w}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </GlassCard>
  );
}

/** "2026-06-21 13:04 UTC", the same in every browser locale. */
function utcMinute(iso: string | null | undefined): string {
  const t = Date.parse(iso ?? "");
  return Number.isNaN(t) ? "unknown time" : `${new Date(t).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function Row({ row }: { row: FunnelRow }) {
  const accentClass =
    row.accent === "green" ? "text-accent-green"
    : row.accent === "amber" ? "text-accent-amber"
    : row.accent === "red" ? "text-accent-red"
    : row.level === 0 ? "text-text-primary font-semibold"
    : "text-text-primary";
  return (
    <tr>
      <td
        className={`py-1.5 px-2 border-b border-border-glass/40 ${
          row.level ? "pl-6 text-text-muted" : "text-text-secondary"
        }`}
      >
        {row.label}
        {row.detail && <span className="ml-1.5 text-xs text-text-muted">({row.detail})</span>}
      </td>
      <td className={`py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums ${accentClass}`}>
        {formatCount(row.count)}
      </td>
    </tr>
  );
}
