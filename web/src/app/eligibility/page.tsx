"use client";

import { Suspense, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  fetchEligibilityPapers,
  eligibilityScreen,
  type EligibilityListResponse,
} from "@/lib/api";
import PaperCard from "@/components/PaperCard";

export default function EligibilityPage() {
  return (
    <Suspense>
      <EligibilityContent />
    </Suspense>
  );
}

function EligibilityContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();

  const [batchSize, setBatchSizeRaw] = useState(() => parseInt(searchParams.get("batch") || "20", 10));

  useEffect(() => {
    const params = new URLSearchParams();
    if (batchSize !== 20) params.set("batch", String(batchSize));
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchSize]);

  const { data, isLoading } = useQuery<EligibilityListResponse>({
    queryKey: ["eligibility-papers", batchSize],
    queryFn: () => fetchEligibilityPapers(batchSize),
    placeholderData: (prev) => prev,
  });

  const mutation = useMutation({
    mutationFn: ({
      id,
      decision,
      reason,
    }: {
      id: string;
      decision: string;
      reason: string;
    }) => eligibilityScreen(id, decision, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eligibility-papers"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const total = data?.total_first_pass_included ?? 0;
  const screened = data?.already_screened ?? 0;
  const remaining = data?.remaining ?? 0;
  const progress = total > 0 ? Math.min((screened / total) * 100, 100) : 0;

  const handleLoadMore = () => {
    setBatchSizeRaw((prev) => prev + 20);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-text-primary">
          Eligibility Screening
        </h1>
        <span className="inline-flex items-center rounded-full bg-accent-purple/15 px-3 py-1 text-sm font-medium text-accent-purple">
          {remaining} remaining
        </span>
      </div>

      <p className="text-text-secondary text-sm">
        Second pass &mdash; apply stricter criteria to first-pass included
        papers
      </p>

      {/* Progress bar */}
      {total > 0 && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-text-muted">
            <span>
              {screened} of {total} screened
            </span>
            <span>{progress.toFixed(1)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-bg-glass">
            <div
              className="h-1.5 rounded-full bg-accent-purple transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading && !data && (
        <p className="text-text-muted text-sm animate-pulse">
          Loading papers...
        </p>
      )}

      {data && data.papers.length === 0 && (
        <div className="glass p-12 text-center">
          <p className="text-text-secondary">
            {total === 0
              ? "No first-pass included papers found. Run screening first."
              : "All papers have been screened for eligibility."}
          </p>
        </div>
      )}

      {/* Paper list */}
      <div className="space-y-4">
        {data?.papers.map((paper) => (
          <PaperCard
            key={paper.id}
            paper={paper}
            mode="eligibility"
            onDecision={(id: string, decision: string, reason: string) =>
              mutation.mutate({ id, decision, reason })
            }
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
