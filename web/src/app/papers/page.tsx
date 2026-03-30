"use client";

import { Suspense, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { fetchAllPapers, searchPapers } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const decisionColor: Record<string, string> = {
  include: "bg-accent-green/15 text-accent-green",
  exclude: "bg-accent-red/15 text-accent-red",
  maybe: "bg-accent-amber/15 text-accent-amber",
};

const sourceColor: Record<string, string> = {
  openalex: "bg-primary/15 text-primary",
  scopus: "bg-accent-green/15 text-accent-green",
  arxiv: "bg-accent-purple/15 text-accent-purple",
  semantic_scholar: "bg-accent-amber/15 text-accent-amber",
};

export default function PapersPage() {
  return (
    <Suspense>
      <PapersContent />
    </Suspense>
  );
}

function PapersContent() {
  const searchParams = useSearchParams();
  const perPage = 25;

  // State initialized from URL params (for back-navigation restore)
  const [page, setPageRaw] = useState(() => parseInt(searchParams.get("page") || "1", 10));
  const [decisionFilter, setDecisionFilterRaw] = useState(() => searchParams.get("decision") || "all");
  const [sourceFilter, setSourceFilterRaw] = useState(() => searchParams.get("source") || "all");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // Sync state to URL for back-navigation persistence
  useEffect(() => {
    const params = new URLSearchParams();
    if (page > 1) params.set("page", String(page));
    if (decisionFilter !== "all") params.set("decision", decisionFilter);
    if (sourceFilter !== "all") params.set("source", sourceFilter);
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [page, decisionFilter, sourceFilter]);

  const setPage = (p: number | ((prev: number) => number)) => setPageRaw(p);
  const setDecisionFilter = (v: string) => { setDecisionFilterRaw(v); setPageRaw(1); };
  const setSourceFilter = (v: string) => { setSourceFilterRaw(v); setPageRaw(1); };

  // Paginated papers from API
  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["all-papers", page, perPage, decisionFilter, sourceFilter],
    queryFn: () => fetchAllPapers(page, perPage, decisionFilter, sourceFilter),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

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
          <option value="openalex">OpenAlex</option>
          <option value="scopus">Scopus</option>
          <option value="arxiv">arXiv</option>
          <option value="semantic_scholar">Semantic Scholar</option>
        </select>
        <div className="ml-auto flex gap-2">
          <a href={`${API}/api/reports/export/csv`} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-accent-green/15 px-4 py-2 text-sm font-medium text-accent-green hover:bg-accent-green/25">
            Export CSV
          </a>
          <a href={`${API}/api/reports/export/bib`} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-accent-purple/15 px-4 py-2 text-sm font-medium text-accent-purple hover:bg-accent-purple/25">
            Export BibTeX
          </a>
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
                <th className="px-5 py-3 font-medium">Title</th>
                <th className="px-5 py-3 font-medium">Authors</th>
                <th className="px-5 py-3 font-medium">Year</th>
                <th className="px-5 py-3 font-medium">Source</th>
                <th className="px-5 py-3 font-medium">Decision</th>
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
                    {paper.authors || "\u2014"}
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
    </div>
  );
}
