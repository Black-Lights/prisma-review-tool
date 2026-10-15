"use client";

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllPapers, searchPapers } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Link from "next/link";
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import ExportModal from "@/components/ExportModal";
import { usePersistedFilters } from "@/hooks/usePersistedFilters";

const decisionColor: Record<string, string> = {
  include: "bg-accent-green/15 text-accent-green",
  exclude: "bg-accent-red/15 text-accent-red",
  maybe: "bg-accent-amber/15 text-accent-amber",
};

const sourceColor: Record<string, string> = {
  arxiv: "bg-accent-amber/15 text-accent-amber",
  crossref: "bg-blue-500/15 text-blue-400",
  openalex: "bg-primary/15 text-primary",
  scopus: "bg-accent-green/15 text-accent-green",
  semantic_scholar: "bg-accent-purple/15 text-accent-purple",
};

export default function PapersPage() {
  return (
    <Suspense>
      <PapersContent />
    </Suspense>
  );
}

const PAPERS_DEFAULTS = { page: 1, decision: "all", source: "all", sort: "", order: "asc", perPage: 25 };

const SORT_COLUMNS: { key: string; label: string; sortable: boolean }[] = [
  { key: "title", label: "Title", sortable: true },
  { key: "authors", label: "Authors", sortable: true },
  { key: "year", label: "Year", sortable: true },
  { key: "source", label: "Source", sortable: true },
  { key: "decision", label: "Decision", sortable: true },
];

function PapersContent() {
  const { filters, setFilter, setFilters } = usePersistedFilters("papers", PAPERS_DEFAULTS);
  const { page, decision: decisionFilter, source: sourceFilter } = filters;
  const sort = String(filters.sort ?? "");
  const order = (filters.order === "desc" ? "desc" : "asc") as "asc" | "desc";
  const perPage = Math.min(1000, Math.max(1, Number(filters.perPage) || 25));

  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [exportFormat, setExportFormat] = useState<"csv" | "bib" | null>(null);

  const setPage = (p: number | ((prev: number) => number)) => {
    const next = typeof p === "function" ? p(page) : p;
    setFilter("page", next);
  };
  const setDecisionFilter = (v: string) => setFilter("decision", v, true);
  const setSourceFilter = (v: string) => setFilter("source", v, true);

  // Paginated papers from API
  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["all-papers", page, perPage, decisionFilter, sourceFilter, sort, order],
    queryFn: () => fetchAllPapers(page, perPage, decisionFilter, sourceFilter, sort, order),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  // Click a column header: same column toggles direction, new column sorts asc.
  // Sorting applies to the paginated browse only (search has its own ordering).
  const handleSort = (key: string) => {
    if (showSearch) return;
    setFilters((prev) => {
      if (prev.sort === key) {
        return { ...prev, order: prev.order === "asc" ? "desc" : "asc", page: 1 };
      }
      return { ...prev, sort: key, order: "asc", page: 1 };
    });
  };

  // Search
  const { data: searchData, isFetching: isSearching } = useQuery({
    queryKey: ["search-papers", searchQuery],
    queryFn: () => searchPapers(searchQuery),
    enabled: searchQuery.length > 0,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput.trim());
  };

  const showSearch = searchQuery.length > 0 && searchData;
  const papers = showSearch ? searchData.papers.map((p) => ({ ...p, authors: "", eligibility: null })) : (data?.papers ?? []);
  const total = showSearch ? searchData.matches : (data?.total ?? 0);
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div data-tutorial="papers-header" className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-text-primary">All Papers</h1>
        <span className="inline-flex items-center rounded-full bg-primary/15 px-3 py-1 text-sm font-medium text-primary">
          {total} {showSearch ? "matches" : "total"}
        </span>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search papers by title, abstract, keywords..."
          className="glass-input flex-1"
        />
        <button type="submit" className="rounded-lg bg-primary/15 px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary/25">
          Search
        </button>
        {searchQuery && (
          <button
            type="button"
            onClick={() => { setSearchQuery(""); setSearchInput(""); }}
            className="rounded-lg bg-accent-red/15 px-4 py-2.5 text-sm font-medium text-accent-red hover:bg-accent-red/25"
          >
            Clear
          </button>
        )}
      </form>

      {/* Filters + Export */}
      <div data-tutorial="papers-filters" className="flex flex-wrap items-center gap-3">
        <select value={decisionFilter} onChange={(e) => { setDecisionFilter(e.target.value); setPage(1); }} className="glass-input text-sm">
          <option value="all">Decision: All</option>
          <option value="include">Included (1st pass)</option>
          <option value="exclude">Excluded</option>
          <option value="maybe">Maybe</option>
          <option disabled className="text-text-muted">── Eligibility ──</option>
          <option value="eligible_included">Eligible: Included</option>
          <option value="eligible_excluded">Eligible: Excluded</option>
        </select>
        <select value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }} className="glass-input text-sm">
          <option value="all">Source: All</option>
          <option value="arxiv">arXiv</option>
          <option value="crossref">Crossref</option>
          <option value="openalex">OpenAlex</option>
          <option value="scopus">Scopus</option>
          <option value="semantic_scholar">Semantic Scholar</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-text-muted">
          <span>Show</span>
          <input
            type="number"
            min={1}
            max={1000}
            value={perPage}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!Number.isNaN(v) && v >= 1) setFilter("perPage", Math.min(1000, v), true);
            }}
            className="glass-input w-20 text-sm"
            title="Rows shown per page (max 1000)"
          />
          <span>per page</span>
        </label>
        <div data-tutorial="export-buttons" className="ml-auto flex gap-2">
          <button onClick={() => setExportFormat("csv")} className="rounded-lg bg-accent-green/15 px-4 py-2 text-sm font-medium text-accent-green hover:bg-accent-green/25">
            Export CSV
          </button>
          <button onClick={() => setExportFormat("bib")} className="rounded-lg bg-accent-purple/15 px-4 py-2 text-sm font-medium text-accent-purple hover:bg-accent-purple/25">
            Export BibTeX
          </button>
        </div>
      </div>

      {/* Loading */}
      {(isLoading || isSearching) && <p className="text-text-muted text-sm animate-pulse">Loading papers...</p>}

      {/* Table */}
      {papers.length > 0 && (
        <GlassCard className="overflow-x-auto !p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-glass text-left text-text-muted">
                {SORT_COLUMNS.map((col) => {
                  const active = sort === col.key;
                  return (
                    <th
                      key={col.key}
                      onClick={() => handleSort(col.key)}
                      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
                      className={`px-5 py-3 font-medium select-none ${
                        showSearch ? "cursor-default" : "cursor-pointer hover:text-text-secondary"
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {col.label}
                        {!showSearch &&
                          (active ? (
                            order === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />
                          ) : (
                            <ChevronsUpDown size={14} className="opacity-30" />
                          ))}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {papers.map((paper, i) => (
                <tr key={paper.id} className={`border-b border-border-glass/50 hover:bg-bg-glass/40 ${i % 2 === 1 ? "bg-bg-glass/20" : ""}`}>
                  <td className="px-5 py-3 max-w-md">
                    <Link href={`/papers/${paper.id}`} className="text-primary hover:underline line-clamp-2">
                      {paper.title}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-text-secondary max-w-[200px] truncate">
                    {paper.authors || "—"}
                  </td>
                  <td className="px-5 py-3 text-text-secondary">{paper.year}</td>
                  <td className="px-5 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceColor[paper.source?.toLowerCase()] ?? "bg-bg-glass text-text-muted"}`}>
                      {paper.source}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    {paper.decision ? (
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${decisionColor[paper.decision.toLowerCase()] ?? "bg-bg-glass text-text-muted"}`}>
                        {paper.decision}
                      </span>
                    ) : (
                      <span className="text-text-muted">&mdash;</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}

      {/* Pagination */}
      {!showSearch && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-text-muted">
            Page {page} of {totalPages} ({total} papers)
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg bg-bg-glass px-3 py-2 text-sm text-text-secondary hover:bg-bg-elevated disabled:opacity-30 border border-border-glass"
            >
              <ChevronLeft size={16} />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4));
              const p = start + i;
              if (p > totalPages) return null;
              return (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`rounded-lg px-3 py-2 text-sm border border-border-glass ${p === page ? "bg-primary/15 text-primary" : "bg-bg-glass text-text-secondary hover:bg-bg-elevated"}`}
                >
                  {p}
                </button>
              );
            })}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-lg bg-bg-glass px-3 py-2 text-sm text-text-secondary hover:bg-bg-elevated disabled:opacity-30 border border-border-glass"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {!isLoading && !isSearching && papers.length === 0 && (
        <div className="glass p-12 text-center">
          <p className="text-text-secondary">No papers match the current filters.</p>
        </div>
      )}

      {/* Export Modal */}
      {exportFormat && (
        <ExportModal
          open={!!exportFormat}
          onClose={() => setExportFormat(null)}
          format={exportFormat}
          totalPapers={total}
          decisionFilter={decisionFilter}
          sourceFilter={sourceFilter}
        />
      )}
    </div>
  );
}
