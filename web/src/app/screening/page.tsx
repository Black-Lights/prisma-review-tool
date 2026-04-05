"use client";

import { Suspense, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import PaperCard from "@/components/PaperCard";
import GlassCard from "@/components/GlassCard";
import { fetchPapersToScreen, screenPaper, searchPapers } from "@/lib/api";
import { usePersistedFilters } from "@/hooks/usePersistedFilters";

type FilterType = "all" | "maybe" | "include" | "exclude";

const FILTER_OPTIONS: { label: string; value: FilterType }[] = [
  { label: "All", value: "all" },
  { label: "Maybe", value: "maybe" },
  { label: "Included", value: "include" },
  { label: "Excluded", value: "exclude" },
];

export default function ScreeningPage() {
  return (
    <Suspense>
      <ScreeningContent />
    </Suspense>
  );
}

const SCREENING_DEFAULTS = { filter: "maybe", batch: 20 } as const;

function ScreeningContent() {
  const queryClient = useQueryClient();

  const { filters, setFilter: setPersistedFilter } = usePersistedFilters("screening", SCREENING_DEFAULTS);
  const filter = filters.filter as FilterType;
  const batchSize = filters.batch;

  const setFilter = (v: FilterType) => {
    setPersistedFilter("filter", v);
    setPersistedFilter("batch", 20);
  };
  const setBatchSize = (fn: (prev: number) => number) => setPersistedFilter("batch", fn(batchSize));
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<any[] | null>(null);

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["papers-to-screen", filter, batchSize],
    queryFn: () => fetchPapersToScreen(batchSize, filter),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const handleDecision = async (id: string, decision: string, reason: string) => {
    await screenPaper(id, decision, reason);
    queryClient.invalidateQueries({ queryKey: ["papers-to-screen"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    setIsSearching(true);
    try {
      const res = await searchPapers(searchQuery);
      setSearchResults(res.papers);
    } finally {
      setIsSearching(false);
    }
  };

  const handleLoadMore = () => {
    setBatchSize((prev) => prev + 20);
  };

  const remaining = data?.total_matching ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div data-tutorial="screening-header" className="flex items-center gap-3">
        <h1 className="text-3xl font-bold text-text-primary tracking-tight">
          Screening
        </h1>
        <span className="rounded-full bg-primary-dim text-primary px-3 py-1 text-sm font-medium">
          {remaining} remaining
        </span>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="relative flex-1">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search papers by title, author, or keyword..."
            className="glass-input w-full"
            style={{ paddingLeft: "2.5rem" }}
          />
        </div>
        <button
          type="submit"
          disabled={isSearching}
          className="px-5 py-2.5 rounded-lg text-sm font-medium bg-primary-dim text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-50 transition-colors cursor-pointer"
        >
          {isSearching ? "Searching..." : "Search"}
        </button>
      </form>

      {/* Search results */}
      {searchResults && (
        <GlassCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-text-primary">
              Search Results ({searchResults.length})
            </h2>
            <button
              onClick={() => {
                setSearchResults(null);
                setSearchQuery("");
              }}
              className="text-sm text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
            >
              Clear
            </button>
          </div>
          <div className="space-y-3">
            {searchResults.map((paper: any) => (
              <div
                key={paper.id}
                className="flex items-center justify-between p-3 rounded-lg bg-bg-glass/50"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate">
                    {paper.title}
                  </p>
                  <p className="text-xs text-text-muted">
                    {paper.year} &middot; {paper.source}
                    {paper.decision && (
                      <span className="ml-2 text-accent-green">{paper.decision}</span>
                    )}
                  </p>
                </div>
              </div>
            ))}
            {searchResults.length === 0 && (
              <p className="text-sm text-text-muted text-center py-4">
                No papers found matching your query.
              </p>
            )}
          </div>
        </GlassCard>
      )}

      {/* Filter pills */}
      <div data-tutorial="filter-pills" className="flex gap-2">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => {
              setFilter(opt.value);
            }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors cursor-pointer ${
              filter === opt.value
                ? "bg-primary/15 text-primary border-primary/30"
                : "bg-bg-glass text-text-secondary border-border-glass hover:border-border-glass-hover"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Paper list */}
      <div className="space-y-4">
        {isLoading && (
          <div className="text-center py-12 text-text-muted">Loading papers...</div>
        )}

        {!isLoading && data?.papers?.length === 0 && (
          <GlassCard className="text-center py-12">
            <p className="text-text-muted">No papers to show for this filter.</p>
          </GlassCard>
        )}

        {data?.papers?.map((paper) => (
          <PaperCard
            key={paper.id}
            paper={paper}
            mode="screen"
            onDecision={handleDecision}
          />
        ))}
      </div>

      {/* Load More */}
      {data?.papers && data.papers.length > 0 && data.papers.length < remaining && (
        <div className="flex justify-center pt-2">
          <button
            onClick={handleLoadMore}
            className="px-6 py-2.5 rounded-lg text-sm font-medium bg-bg-glass text-text-secondary border border-border-glass hover:border-border-glass-hover transition-colors cursor-pointer"
          >
            Load More
          </button>
        </div>
      )}
    </div>
  );
}
