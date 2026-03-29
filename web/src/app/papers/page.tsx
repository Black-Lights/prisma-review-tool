"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPapersToScreen,
  searchPapers,
  type PaperListResponse,
  type SearchResponse,
} from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const decisionColor: Record<string, string> = {
  included: "bg-accent-green/15 text-accent-green",
  excluded: "bg-accent-red/15 text-accent-red",
  maybe: "bg-accent-amber/15 text-accent-amber",
};

const sourceColor: Record<string, string> = {
  openalex: "bg-primary/15 text-primary",
  arxiv: "bg-accent-purple/15 text-accent-purple",
  semantic_scholar: "bg-accent-amber/15 text-accent-amber",
};

export default function PapersPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [decisionFilter, setDecisionFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  // Fetch all papers
  const { data, isLoading, error } = useQuery<PaperListResponse>({
    queryKey: ["all-papers"],
    queryFn: () => fetchPapersToScreen(100, "all"),
  });

  // Search query
  const {
    data: searchData,
    isFetching: isSearching,
  } = useQuery<SearchResponse>({
    queryKey: ["search-papers", searchQuery],
    queryFn: () => searchPapers(searchQuery),
    enabled: searchQuery.length > 0,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput.trim());
  };

  // Determine which papers to show
  const papers = useMemo(() => {
    if (searchQuery && searchData) {
      return searchData.papers.map((p) => ({
        ...p,
        authors: "",
        source: p.source ?? "",
        current_decision: p.decision,
      }));
    }
    return data?.papers ?? [];
  }, [searchQuery, searchData, data]);

  // Client-side filtering
  const filtered = useMemo(() => {
    return papers.filter((p) => {
      const decision = (
        "current_decision" in p ? p.current_decision : null
      ) as string | null;

      if (
        decisionFilter !== "all" &&
        (decision ?? "").toLowerCase() !== decisionFilter
      ) {
        return false;
      }
      if (
        sourceFilter !== "all" &&
        (p.source ?? "").toLowerCase() !== sourceFilter
      ) {
        return false;
      }
      return true;
    });
  }, [papers, decisionFilter, sourceFilter]);

  const totalCount = data?.total_matching ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-text-primary">All Papers</h1>
        <span className="inline-flex items-center rounded-full bg-primary/15 px-3 py-1 text-sm font-medium text-primary">
          {totalCount} total
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
        <button
          type="submit"
          className="rounded-lg bg-primary/15 px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary/25 transition-colors"
        >
          Search
        </button>
      </form>

      {/* Filters + Export */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={decisionFilter}
          onChange={(e) => setDecisionFilter(e.target.value)}
          className="glass-input text-sm"
        >
          <option value="all">Decision: All</option>
          <option value="included">Included</option>
          <option value="excluded">Excluded</option>
          <option value="maybe">Maybe</option>
        </select>

        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="glass-input text-sm"
        >
          <option value="all">Source: All</option>
          <option value="openalex">OpenAlex</option>
          <option value="arxiv">arXiv</option>
          <option value="semantic_scholar">Semantic Scholar</option>
        </select>

        <div className="ml-auto flex gap-2">
          <a
            href={`${API}/api/reports/export/csv`}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-accent-green/15 px-4 py-2 text-sm font-medium text-accent-green hover:bg-accent-green/25 transition-colors"
          >
            Export CSV
          </a>
          <a
            href={`${API}/api/reports/export/bib`}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-accent-purple/15 px-4 py-2 text-sm font-medium text-accent-purple hover:bg-accent-purple/25 transition-colors"
          >
            Export BibTeX
          </a>
        </div>
      </div>

      {/* Loading / Error */}
      {(isLoading || isSearching) && (
        <p className="text-text-muted text-sm animate-pulse">
          Loading papers...
        </p>
      )}

      {error && (
        <p className="text-accent-red text-sm">Failed to load papers.</p>
      )}

      {/* Table */}
      {filtered.length > 0 && (
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
              {filtered.map((paper, i) => {
                const decision = (
                  "current_decision" in paper ? paper.current_decision : null
                ) as string | null;
                const authors =
                  "authors" in paper
                    ? (paper.authors as string)
                    : "";

                return (
                  <tr
                    key={paper.id}
                    className={`border-b border-border-glass/50 hover:bg-bg-glass/40 ${
                      i % 2 === 1 ? "bg-bg-glass/20" : ""
                    }`}
                  >
                    <td className="px-5 py-3 max-w-md">
                      <Link
                        href={`/papers/${paper.id}`}
                        className="text-primary hover:underline line-clamp-2"
                      >
                        {paper.title}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-text-secondary max-w-[200px] truncate">
                      {authors || "\u2014"}
                    </td>
                    <td className="px-5 py-3 text-text-secondary">
                      {paper.year}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          sourceColor[paper.source?.toLowerCase()] ??
                          "bg-bg-glass text-text-muted"
                        }`}
                      >
                        {paper.source}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {decision ? (
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            decisionColor[decision.toLowerCase()] ??
                            "bg-bg-glass text-text-muted"
                          }`}
                        >
                          {decision}
                        </span>
                      ) : (
                        <span className="text-text-muted">&mdash;</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </GlassCard>
      )}

      {!isLoading && !isSearching && filtered.length === 0 && (
        <div className="glass p-12 text-center">
          <p className="text-text-secondary">
            No papers match the current filters.
          </p>
        </div>
      )}
    </div>
  );
}
