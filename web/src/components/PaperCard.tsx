"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Info } from "lucide-react";
import type { PaperSummary } from "@/lib/api";

const sourceBadgeColors: Record<string, string> = {
  openalex: "bg-primary-dim text-primary",
  arxiv: "bg-accent-amber/15 text-accent-amber",
  semantic_scholar: "bg-accent-green/15 text-accent-green",
};

interface PaperCardProps {
  paper: PaperSummary;
  onDecision: (id: string, decision: string, reason: string) => void;
  mode?: "screen" | "eligibility";
}

export default function PaperCard({ paper, onDecision, mode = "screen" }: PaperCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");

  const hasDecision = paper.current_decision && paper.current_decision !== "maybe";
  const sourceClass = sourceBadgeColors[paper.source] ?? "bg-bg-glass text-text-secondary";

  return (
    <div className="glass p-5 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-bold text-text-primary leading-snug flex-1">
          {paper.title}
        </h3>
        <span className="shrink-0 rounded-full bg-bg-glass px-2.5 py-0.5 text-xs text-text-secondary">
          {paper.year}
        </span>
      </div>

      {/* Authors */}
      <p className="text-sm text-text-secondary truncate">{paper.authors}</p>

      {/* Source badge */}
      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${sourceClass}`}>
        {paper.source}
      </span>

      {/* Abstract */}
      <div>
        <p className={`text-sm text-text-secondary leading-relaxed ${expanded ? "" : "line-clamp-3"}`}>
          {paper.abstract}
        </p>
        {paper.abstract && paper.abstract.length > 200 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1 flex items-center gap-1 text-xs text-primary hover:text-primary/80"
          >
            {expanded ? (
              <>
                Show less <ChevronUp size={14} />
              </>
            ) : (
              <>
                Show more <ChevronDown size={14} />
              </>
            )}
          </button>
        )}
      </div>

      {/* First-pass info (eligibility mode) */}
      {mode === "eligibility" && paper.screen_reason && (
        <div className="flex items-start gap-2 rounded-lg bg-primary-dim p-3">
          <Info size={16} className="text-primary mt-0.5 shrink-0" />
          <div className="text-xs">
            <span className="font-semibold text-primary">First-pass screening:</span>{" "}
            <span className="text-text-secondary">{paper.screen_reason}</span>
          </div>
        </div>
      )}

      {/* Existing decision badge */}
      {hasDecision && (
        <div
          className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${
            paper.current_decision === "include"
              ? "bg-accent-green/15 text-accent-green"
              : "bg-accent-red/15 text-accent-red"
          }`}
        >
          {paper.current_decision === "include" ? "Included" : "Excluded"}
          {paper.current_reason && (
            <span className="ml-1.5 font-normal text-text-muted">— {paper.current_reason}</span>
          )}
        </div>
      )}

      {/* Decision controls */}
      {!hasDecision && (
        <div className="flex items-center gap-3 pt-1">
          <input
            type="text"
            placeholder="Reason for decision..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="glass-input flex-1 text-sm"
          />
          <button
            onClick={() => onDecision(paper.id, "include", reason)}
            className="rounded-lg bg-accent-green/90 hover:bg-accent-green px-4 py-2 text-sm font-semibold text-bg-base transition-colors"
          >
            Include
          </button>
          <button
            onClick={() => onDecision(paper.id, "exclude", reason)}
            className="rounded-lg border border-accent-red/50 hover:border-accent-red text-accent-red px-4 py-2 text-sm font-semibold transition-colors"
          >
            Exclude
          </button>
        </div>
      )}
    </div>
  );
}
