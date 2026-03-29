"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchEligibilityPapers,
  eligibilityScreen,
  type EligibilityListResponse,
} from "@/lib/api";
import PaperCard from "@/components/PaperCard";

export default function EligibilityPage() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<EligibilityListResponse>({
    queryKey: ["eligibility-papers"],
    queryFn: () => fetchEligibilityPapers(20),
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
    },
  });

  const total = data?.total_first_pass_included ?? 0;
  const screened = data?.already_screened ?? 0;
  const remaining = data?.remaining ?? 0;
  const progress = total > 0 ? (screened / total) * 100 : 0;

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

      {/* Content */}
      {isLoading && (
        <p className="text-text-muted text-sm animate-pulse">
          Loading papers...
        </p>
      )}

      {error && (
        <p className="text-accent-red text-sm">
          Failed to load eligibility papers.
        </p>
      )}

      {data && data.papers.length === 0 && (
        <div className="glass p-12 text-center">
          <p className="text-text-secondary">
            No papers remaining for eligibility screening.
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
            onDecision={(decision: string, reason: string) =>
              mutation.mutate({ id: paper.id, decision, reason })
            }
          />
        ))}
      </div>
    </div>
  );
}
