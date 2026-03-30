"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchPaper, type PaperDetail } from "@/lib/api";
import GlassCard from "@/components/GlassCard";

const methodColor: Record<string, string> = {
  rule: "bg-primary/15 text-primary",
  ai: "bg-accent-purple/15 text-accent-purple",
  manual: "bg-accent-green/15 text-accent-green",
};

const decisionColor: Record<string, string> = {
  included: "text-accent-green",
  excluded: "text-accent-red",
  maybe: "text-accent-amber",
};

export default function PaperDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { data: paper, isLoading, error } = useQuery<PaperDetail>({
    queryKey: ["paper", id],
    queryFn: () => fetchPaper(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <p className="text-text-muted animate-pulse">Loading paper...</p>
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <button
          onClick={() => router.back()}
          className="text-primary hover:underline text-sm cursor-pointer"
        >
          &larr; Go Back
        </button>
        <p className="text-accent-red">Failed to load paper details.</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Back link */}
      <button
        onClick={() => router.back()}
        className="inline-flex items-center gap-1 text-primary hover:underline text-sm cursor-pointer"
      >
        &larr; Go Back
      </button>

      {/* Title */}
      <h1 className="text-2xl font-bold text-text-primary leading-snug">
        {paper.title}
      </h1>

      {/* DOI */}
      {paper.doi && (
        <a
          href={`https://doi.org/${paper.doi}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary hover:underline break-all"
        >
          DOI: {paper.doi}
        </a>
      )}

      {/* Metadata row */}
      <div className="flex flex-wrap items-center gap-3 text-sm text-text-secondary">
        {paper.year && <span>{paper.year}</span>}
        {paper.venue && (
          <>
            <span className="text-text-muted">|</span>
            <span>{paper.venue}</span>
          </>
        )}
        <span className="text-text-muted">|</span>
        <span className="inline-flex items-center rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
          {paper.source}
        </span>
      </div>

      {/* Authors */}
      {paper.authors && paper.authors.length > 0 && (
        <div className="space-y-1">
          <h2 className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Authors
          </h2>
          <p className="text-sm text-text-secondary leading-relaxed">
            {paper.authors.join(", ")}
          </p>
        </div>
      )}

      {/* Abstract */}
      {paper.abstract && (
        <div className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Abstract
          </h2>
          <p className="text-base leading-relaxed text-text-primary">
            {paper.abstract}
          </p>
        </div>
      )}

      {/* Keywords */}
      {paper.keywords && paper.keywords.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Keywords
          </h2>
          <div className="flex flex-wrap gap-2">
            {paper.keywords.map((kw, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full bg-bg-glass px-3 py-1 text-xs font-medium text-text-secondary border border-border-glass"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Screening History */}
      <div className="space-y-3">
        <h2 className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Screening History
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* First-pass screening */}
          <GlassCard className="space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">
              First-Pass Screening
            </h3>
            {paper.screen_decision ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">Decision:</span>
                  <span
                    className={`text-sm font-medium ${
                      decisionColor[paper.screen_decision.toLowerCase()] ??
                      "text-text-secondary"
                    }`}
                  >
                    {paper.screen_decision}
                  </span>
                </div>
                {paper.screen_method && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-muted">Method:</span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        methodColor[paper.screen_method.toLowerCase()] ??
                        "bg-bg-glass text-text-muted"
                      }`}
                    >
                      {paper.screen_method}
                    </span>
                  </div>
                )}
                {paper.screen_reason && (
                  <p className="text-xs text-text-secondary leading-relaxed">
                    {paper.screen_reason}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-text-muted">Not yet screened</p>
            )}
          </GlassCard>

          {/* Eligibility screening */}
          <GlassCard className="space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">
              Eligibility Screening
            </h3>
            {paper.eligibility_decision ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">Decision:</span>
                  <span
                    className={`text-sm font-medium ${
                      decisionColor[
                        paper.eligibility_decision.toLowerCase()
                      ] ?? "text-text-secondary"
                    }`}
                  >
                    {paper.eligibility_decision}
                  </span>
                </div>
                {paper.eligibility_method && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-muted">Method:</span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        methodColor[
                          paper.eligibility_method.toLowerCase()
                        ] ?? "bg-bg-glass text-text-muted"
                      }`}
                    >
                      {paper.eligibility_method}
                    </span>
                  </div>
                )}
                {paper.eligibility_reason && (
                  <p className="text-xs text-text-secondary leading-relaxed">
                    {paper.eligibility_reason}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-text-muted">Not yet screened</p>
            )}
          </GlassCard>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3 pt-2">
        {paper.doi && (
          <a
            href={`https://doi.org/${paper.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-primary/15 px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary/25 transition-colors"
          >
            Open DOI
          </a>
        )}
        {paper.url && (
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-bg-glass px-5 py-2.5 text-sm font-medium text-text-secondary border border-border-glass hover:border-border-glass-hover transition-colors"
          >
            Open URL
          </a>
        )}
      </div>
    </div>
  );
}
