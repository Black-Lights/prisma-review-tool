"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Square, CheckCircle2, XCircle, Ban } from "lucide-react";
import { fetchPipelineProgress, stopPipeline, PipelineProgress as ProgressType } from "@/lib/api";
import Modal from "@/components/Modal";

const STEP_LABELS: Record<string, string> = {
  search: "Searching databases",
  dedup: "Removing duplicates",
  screen: "Keyword screening",
};

function elapsed(startedAt: string | null): string {
  if (!startedAt) return "";
  const ms = Date.now() - new Date(startedAt).getTime();
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  return `${mins}m ${remSecs}s`;
}

interface PipelineProgressProps {
  /** Called when the pipeline finishes (completed, failed, or cancelled). */
  onFinished?: (status: ProgressType["status"]) => void;
}

export default function PipelineProgress({ onFinished }: PipelineProgressProps) {
  const queryClient = useQueryClient();
  const [showStopModal, setShowStopModal] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [elapsedStr, setElapsedStr] = useState("");

  const { data: progress } = useQuery({
    queryKey: ["pipeline-progress"],
    queryFn: fetchPipelineProgress,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Poll every 2s while running, then stop
      return status === "running" ? 2000 : false;
    },
  });

  const isRunning = progress?.status === "running";
  const isTerminal = progress?.status === "completed" || progress?.status === "failed" || progress?.status === "cancelled";

  // Update elapsed time every second while running
  useEffect(() => {
    if (!isRunning || !progress?.started_at) return;
    setElapsedStr(elapsed(progress.started_at));
    const timer = setInterval(() => {
      setElapsedStr(elapsed(progress.started_at));
    }, 1000);
    return () => clearInterval(timer);
  }, [isRunning, progress?.started_at]);

  // Notify parent when pipeline finishes & refresh stats
  useEffect(() => {
    if (isTerminal && progress) {
      onFinished?.(progress.status);
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTerminal]);

  const handleStop = async () => {
    setStopping(true);
    try {
      await stopPipeline();
      // Immediately refetch progress to show updated state
      queryClient.invalidateQueries({ queryKey: ["pipeline-progress"] });
    } finally {
      setStopping(false);
    }
  };

  // Don't render anything when idle and no session has ever been started
  if (!progress || (progress.status === "idle" && !progress.session_id)) {
    return null;
  }

  const statusIcon = () => {
    switch (progress.status) {
      case "running":
        return <Loader2 size={18} className="animate-spin text-primary" />;
      case "completed":
        return <CheckCircle2 size={18} className="text-accent-green" />;
      case "failed":
        return <XCircle size={18} className="text-accent-red" />;
      case "cancelled":
        return <Ban size={18} className="text-accent-amber" />;
      default:
        return null;
    }
  };

  const statusColor = () => {
    switch (progress.status) {
      case "running": return "border-primary/30 bg-primary/5";
      case "completed": return "border-accent-green/30 bg-accent-green/5";
      case "failed": return "border-accent-red/30 bg-accent-red/5";
      case "cancelled": return "border-accent-amber/30 bg-accent-amber/5";
      default: return "border-border-glass bg-bg-glass";
    }
  };

  const stepLabel = progress.current_step ? STEP_LABELS[progress.current_step] ?? progress.current_step : null;

  return (
    <>
      <div className={`rounded-lg border p-4 ${statusColor()} transition-colors`}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {statusIcon()}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-text-primary truncate">
                  {progress.progress_message ?? "Pipeline"}
                </p>
                {isRunning && elapsedStr && (
                  <span className="text-xs text-text-muted shrink-0">{elapsedStr}</span>
                )}
              </div>
              {isRunning && stepLabel && (
                <p className="text-xs text-text-secondary mt-0.5">
                  Step: {stepLabel}
                </p>
              )}
            </div>
          </div>

          {isRunning && (
            <button
              onClick={() => setShowStopModal(true)}
              disabled={stopping}
              className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent-red/15 text-accent-red border border-accent-red/20 hover:bg-accent-red/25 disabled:opacity-50 transition-colors cursor-pointer"
            >
              <Square size={12} />
              Stop
            </button>
          )}
        </div>

        {/* Progress bar for running state */}
        {isRunning && (
          <div className="mt-3 h-1 rounded-full bg-bg-glass overflow-hidden">
            <div className="h-full rounded-full bg-primary animate-pulse w-full origin-left" style={{ animation: "indeterminate 1.5s ease-in-out infinite" }} />
          </div>
        )}

        {/* Warnings */}
        {progress.warnings?.length > 0 && (
          <div className="mt-2 space-y-1">
            {progress.warnings.map((w, i) => (
              <p key={i} className="text-xs text-accent-amber">
                ⚠ {w}
              </p>
            ))}
          </div>
        )}
      </div>

      <Modal
        open={showStopModal}
        onClose={() => setShowStopModal(false)}
        onConfirm={handleStop}
        variant="danger"
        title="Stop pipeline?"
        description="The pipeline will stop after the current step finishes. Results from completed steps will be preserved."
        confirmLabel="Yes, stop pipeline"
        cancelLabel="Keep running"
      />

      <style jsx>{`
        @keyframes indeterminate {
          0% { transform: scaleX(0.3) translateX(-100%); }
          50% { transform: scaleX(0.5) translateX(50%); }
          100% { transform: scaleX(0.3) translateX(200%); }
        }
      `}</style>
    </>
  );
}
