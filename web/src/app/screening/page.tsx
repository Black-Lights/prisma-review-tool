"use client";

import { Suspense, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, RefreshCw, SlidersHorizontal } from "lucide-react";
import PaperCard from "@/components/PaperCard";
import GlassCard from "@/components/GlassCard";
import { fetchPapersToScreen, screenPaper, searchPapers, rescreenPapers, fetchStats, fetchConfig, updateConfig } from "@/lib/api";
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

  // Re-screen
  const [showRescreen, setShowRescreen] = useState(false);

  // Load current config + stats
  const { data: configData } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
    staleTime: 30_000,
  });
  const { data: statsData } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    staleTime: 30_000,
  });
  const configMinHits = configData?.screening?.rules?.min_include_hits ?? 2;
  const screenStats = (statsData as any)?.screen ?? {};

  const [rescreenHits, setRescreenHits] = useState<number | null>(null);
  // Sync with config once loaded
  const effectiveHits = rescreenHits ?? configMinHits;

  const rescreenMutation = useMutation({
    mutationFn: async (hits: number) => {
      const result = await rescreenPapers(hits);
      // Save the new threshold to config so Settings page stays in sync
      if (configData) {
        const updated = { ...configData };
        if (!updated.screening) updated.screening = { rules: {} };
        if (!updated.screening.rules) updated.screening.rules = {};
        updated.screening.rules.min_include_hits = hits;
        await updateConfig(updated);
      }
      return result;
    },
    onSuccess: () => {
      // Invalidate everything — screening changes affect all pages
      queryClient.invalidateQueries();
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div data-tutorial="screening-header" className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-text-primary tracking-tight">
            Screening
          </h1>
          <span className="rounded-full bg-primary-dim text-primary px-3 py-1 text-sm font-medium">
            {remaining} remaining
          </span>
        </div>
        <button
          onClick={() => setShowRescreen(!showRescreen)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-bg-glass text-text-secondary border border-border-glass hover:border-border-glass-hover transition-colors cursor-pointer"
        >
          <SlidersHorizontal size={16} />
          Re-screen
        </button>
      </div>

      {/* Re-screen panel */}
      {showRescreen && (
        <GlassCard data-tutorial="rescreen-panel" className="!p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-primary" />
              <span className="text-sm font-medium text-text-primary">Re-run keyword screening</span>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-text-secondary">Min keyword hits:</label>
              <input
                type="number"
                min={1}
                max={10}
                value={effectiveHits}
                onChange={(e) => setRescreenHits(parseInt(e.target.value) || 1)}
                className="glass-input w-20 text-center text-sm"
              />
              <div className="relative group">
                <button className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 text-[10px] font-bold">i</button>
                <div className="absolute left-0 bottom-7 w-64 glass-elevated p-3 rounded-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible z-50 text-xs space-y-1 shadow-xl">
                  <p className="text-text-primary font-medium">How many include keywords must match</p>
                  <p className="text-text-muted">Low (1-2) = more papers pass, permissive</p>
                  <p className="text-text-muted">High (3-5) = fewer papers, stricter</p>
                </div>
              </div>
            </div>
            {screenStats.included !== undefined && (
              <span className="text-xs text-text-muted">
                Currently: {screenStats.included} included / {screenStats.maybe} maybe / {screenStats.excluded} excluded
              </span>
            )}
            <button
              onClick={() => rescreenMutation.mutate(effectiveHits)}
              disabled={rescreenMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary/15 text-primary border border-primary/20 hover:bg-primary/25 disabled:opacity-50 transition-colors cursor-pointer ml-auto"
            >
              <RefreshCw size={14} className={rescreenMutation.isPending ? "animate-spin" : ""} />
              {rescreenMutation.isPending ? "Re-screening..." : "Apply"}
            </button>
          </div>
          {rescreenMutation.data && (
            <div className="mt-3 p-3 rounded-lg bg-accent-green/10 border border-accent-green/20">
              <p className="text-sm text-accent-green font-medium">
                Re-screening complete (min hits = {rescreenMutation.data.min_include_hits})
              </p>
              <p className="text-xs text-text-secondary mt-1">
                {rescreenMutation.data.included} included {"\u00B7"} {rescreenMutation.data.maybe} maybe {"\u00B7"} {rescreenMutation.data.excluded} excluded
                {" \u2014 "} {rescreenMutation.data.included} papers moved to Eligibility page
              </p>
            </div>
          )}
        </GlassCard>
      )}

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
