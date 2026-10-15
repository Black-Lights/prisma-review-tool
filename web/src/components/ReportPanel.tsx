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

/**
 * Read-only pipeline report: what came in, what was filtered, and how.
 * Draws entirely from data already exposed by the API (stats funnel, config
 * filters, and the last run's transparency warnings) — no backend changes.
 */
export default function ReportPanel() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: fetchStats, staleTime: 30_000 });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig, staleTime: 30_000 });
  const { data: progress } = useQuery({
    queryKey: ["pipeline-progress-report"],
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

  const s: any = stats ?? {};
  const hasData = s && !s.error && s.search && Object.keys(s.search).length > 0;

  const search: Record<string, number> = s.search ?? {};
  const dedup: Record<string, number> = s.dedup ?? {};
  const screen: Record<string, number> = s.screen ?? {};
  const eligibility: Record<string, number> = s.eligibility ?? {};

  const perSource = Object.entries(search).filter(([k]) => k !== "total");
  const totalFound = search.total ?? perSource.reduce((acc, [, v]) => acc + (v || 0), 0);

  const dupRemoved = dedup.duplicates_removed ?? 0;
  const afterDedup = dedup.remaining ?? 0;

  const included = screen.included ?? 0;
  const maybe = screen.maybe ?? 0;
  const excluded = screen.excluded ?? 0;
  const excludedGate = screen.excluded_no_required_keyword ?? 0;
  const excludedByKeyword = Math.max(0, excluded - excludedGate);

  const filters = config?.search?.filters ?? {};
  const dateRange = config?.search?.date_range ?? {};
  const minHits = config?.screening?.rules?.min_include_hits ?? 2;
  const warnings: string[] = progress?.warnings ?? [];

  const queryRows = byQuery?.queries ?? [];
  const untaggedScreened = byQuery?.untagged?.screened ?? 0;
  const hasQueryData = queryRows.length > 0;

  const planSources = filterPlan?.sources ?? [];
  const planRows = filterPlan?.filters ?? [];
  const hasPlanData = !filterPlan?.empty && planRows.length > 0;

  // request = filtered at the source; post = filtered locally after the call;
  // unsupported = the source can't express it, so it's ignored there.
  const modeLabel: Record<FilterMode, string> = {
    request: "At source",
    post: "After call",
    unsupported: "Ignored",
  };
  const modeClass: Record<FilterMode, string> = {
    request: "text-accent-green",
    post: "text-accent-amber",
    unsupported: "text-text-muted",
  };

  const fmt = (n: number) => (n ?? 0).toLocaleString();
  const valueOf = (v: any): string => {
    if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
    if (typeof v === "boolean") return v ? "on" : "off";
    return v ? String(v) : "—";
  };

  const filterRows: [string, string][] = [
    ["Date range", `${dateRange.start ?? "?"} → ${dateRange.end ?? "?"}`],
    ["Document types", valueOf(filters.document_types)],
    ["Require abstract", valueOf(filters.require_abstract)],
    ["Open access", valueOf(filters.open_access)],
    ["Venues / ISSN", valueOf(filters.venues)],
  ];

  const buildMarkdown = (): string => {
    const project = config?.project?.name ?? "PRISMA Review";
    const L: string[] = [];
    L.push(`# Search report — ${project}`, "");
    L.push("## Funnel", "", "| Stage | Count |", "| --- | ---: |");
    L.push(`| Records found (search) | ${fmt(totalFound)} |`);
    perSource.forEach(([src, n]) => L.push(`| · ${src} | ${fmt(n)} |`));
    L.push(`| After deduplication | ${fmt(afterDedup)} (− ${fmt(dupRemoved)} duplicates) |`);
    L.push(`| Screened → Included | ${fmt(included)} |`);
    L.push(`| Screened → Maybe | ${fmt(maybe)} |`);
    L.push(`| Screened → Excluded | ${fmt(excluded)} |`);
    if (eligibility && Object.keys(eligibility).length) {
      L.push(`| Eligibility → Included | ${fmt(eligibility.included ?? 0)} |`);
    }
    if (hasQueryData) {
      L.push("", "## Results per query (with overlap — queries are OR'd)", "");
      L.push("| Query | Found (raw) | After dedup | Included | Maybe | Excluded |");
      L.push("| --- | ---: | ---: | ---: | ---: | ---: |");
      queryRows.forEach((q) =>
        L.push(`| ${q.name} | ${fmt(q.found_raw)} | ${fmt(q.after_dedup)} | ${fmt(q.included)} | ${fmt(q.maybe)} | ${fmt(q.excluded)} |`),
      );
      L.push(
        "",
        `_A paper matched by several queries is counted under each, so column sums exceed the ${fmt(byQuery?.total_included ?? included)} distinct included._`,
      );
      if (untaggedScreened > 0) {
        L.push(`_${fmt(untaggedScreened)} screened paper(s) carry no query tag (searched before per-query tracking); re-run the search to attribute them._`);
      }
    }

    L.push("", "## Source filters", "", "| Filter | Value |", "| --- | --- |");
    filterRows.forEach(([k, v]) => L.push(`| ${k} | ${v} |`));

    if (hasPlanData) {
      L.push("", "## Where each filter is applied", "");
      L.push(`| Filter | ${planSources.join(" | ")} |`);
      L.push(`| --- | ${planSources.map(() => "---").join(" | ")} |`);
      planRows.forEach((row) =>
        L.push(`| ${row.filter} | ${planSources.map((s) => modeLabel[row.by_source[s] ?? "unsupported"]).join(" | ")} |`),
      );
      L.push("", "_At source = sent in the request (server-side). After call = enforced locally after fetch. Ignored = source can't express it._");
    }
    L.push("", "## Screening breakdown", "", "| Outcome | Count |", "| --- | ---: |");
    L.push(`| Excluded by exclude keyword | ${fmt(excludedByKeyword)} |`);
    L.push(`| Excluded by required-keyword gate | ${fmt(excludedGate)} |`);
    L.push(`| Included (≥ ${minHits} keyword hits) | ${fmt(included)} |`);
    L.push(`| Maybe (< ${minHits} hits, needs review) | ${fmt(maybe)} |`);
    if (warnings.length) {
      L.push("", "## Transparency warnings (last run)", "");
      warnings.forEach((w) => L.push(`- ${w}`));
    }
    return L.join("\n");
  };

  const handleExport = () => {
    const md = buildMarkdown();
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
          {/* 1) Funnel */}
          <section>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2">
              Funnel — what came in, what survived each stage
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-muted">
                    <th className="font-medium py-1.5 px-2 border-b border-border-glass">Stage</th>
                    <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Count</th>
                    <th className="font-medium py-1.5 px-2 border-b border-border-glass text-right">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  <Row label="Records found (search)" count={fmt(totalFound)} strong />
                  {perSource.map(([src, n]) => (
                    <Row key={src} label={`· ${src}`} count={fmt(n)} muted indent />
                  ))}
                  <Row label="After deduplication" count={fmt(afterDedup)} delta={`− ${fmt(dupRemoved)} dup`} />
                  <Row label="Screened → Included" count={fmt(included)} accent="green" />
                  <Row label="Screened → Maybe" count={fmt(maybe)} accent="amber" />
                  <Row label="Screened → Excluded" count={fmt(excluded)} accent="red" />
                  {eligibility && eligibility.included !== undefined && (
                    <Row label="Eligibility → Included" count={fmt(eligibility.included)} accent="green" />
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* 1.5) Results per query */}
          {hasQueryData && (
            <section>
              <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2 flex items-center gap-1.5">
                <Layers size={13} className="text-primary" />
                Results per query — how many of each query reached each stage
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
                    {queryRows.map((q) => (
                      <tr key={q.name}>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-text-secondary font-mono text-xs" title={q.terms}>
                          {q.name}
                        </td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-text-muted">{fmt(q.found_raw)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-text-primary">{fmt(q.after_dedup)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-green">{fmt(q.included)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-amber">{fmt(q.maybe)}</td>
                        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums text-accent-red">{fmt(q.excluded)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-text-muted mt-2">
                A paper matched by several queries is counted under each (queries are OR&apos;d), so the columns
                sum to more than the {fmt(byQuery?.total_included ?? included)} distinct included.
                {untaggedScreened > 0 && (
                  <>
                    {" "}
                    <span className="text-accent-amber">
                      {fmt(untaggedScreened)} paper(s) have no query tag — re-run the search to attribute them.
                    </span>
                  </>
                )}
              </p>
            </section>
          )}

          {/* 2) Source filters */}
          <section>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2">
              Source filters — how the request was narrowed
            </h3>
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
                  Where each filter is applied — at the source vs. after the call
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
                                {modeLabel[mode]}
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
                No active source filters. See “Transparency warnings” below for query-degradation notes.
              </p>
            )}
          </section>

          {/* 3) Screening breakdown */}
          <section>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-2">
              Screening — how records were classified
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <tbody>
                  <Row label="Excluded by exclude keyword" count={fmt(excludedByKeyword)} accent="red" />
                  <Row label="Excluded by required-keyword gate" count={fmt(excludedGate)} accent="red" />
                  <Row label={`Included (≥ ${minHits} keyword hits)`} count={fmt(included)} accent="green" />
                  <Row label={`Maybe (< ${minHits} hits, needs review)`} count={fmt(maybe)} accent="amber" />
                </tbody>
              </table>
            </div>
          </section>

          {/* 4) Transparency warnings */}
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

function Row({
  label,
  count,
  delta,
  strong,
  muted,
  indent,
  accent,
}: {
  label: string;
  count: string;
  delta?: string;
  strong?: boolean;
  muted?: boolean;
  indent?: boolean;
  accent?: "green" | "amber" | "red";
}) {
  const accentClass =
    accent === "green" ? "text-accent-green"
    : accent === "amber" ? "text-accent-amber"
    : accent === "red" ? "text-accent-red"
    : strong ? "text-text-primary font-semibold"
    : "text-text-primary";
  return (
    <tr>
      <td className={`py-1.5 px-2 border-b border-border-glass/40 ${muted ? "text-text-muted" : "text-text-secondary"} ${indent ? "pl-5" : ""}`}>
        {label}
      </td>
      <td className={`py-1.5 px-2 border-b border-border-glass/40 text-right tabular-nums ${accentClass}`}>
        {count}
      </td>
      {delta !== undefined ? (
        <td className="py-1.5 px-2 border-b border-border-glass/40 text-right text-xs text-text-muted">{delta}</td>
      ) : (
        <td className="py-1.5 px-2 border-b border-border-glass/40" />
      )}
    </tr>
  );
}
