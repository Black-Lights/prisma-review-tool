"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Play, Square } from "lucide-react";
import StatCard from "@/components/StatCard";
import GlassCard from "@/components/GlassCard";
import PipelineProgress from "@/components/PipelineProgress";
import PrismaFlowDiagram from "@/components/PrismaFlowDiagram";
import {
  fetchStats,
  startPipeline,
  fetchPipelineProgress,
  PipelineStatusType,
} from "@/lib/api";
import Modal from "@/components/Modal";
import { useState, useCallback } from "react";

const PIPELINE_STEPS = [
  { key: "search", label: "Search Databases", statPath: "search.total" },
  { key: "dedup", label: "Deduplicate", statPath: "dedup.remaining" },
  { key: "screen", label: "Keyword Screening", statPath: "screen.included" },
  { key: "eligibility", label: "Eligibility", statPath: "eligibility.included" },
  { key: "export", label: "Export & Download", statPath: null },
] as const;

function getNestedValue(obj: any, path: string | null): number | null {
  if (!path || !obj) return null;
  const keys = path.split(".");
  let val = obj;
  for (const k of keys) {
    val = val?.[k];
  }
  return typeof val === "number" ? val : null;
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [showRunAllModal, setShowRunAllModal] = useState(false);

  // Check if pipeline is already running on mount
  const { data: progress } = useQuery({
    queryKey: ["pipeline-progress"],
    queryFn: fetchPipelineProgress,
  });

  const isPipelineRunning = progress?.status === "running";

  const { data: stats, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    // Refetch stats while pipeline runs so counts update as steps complete
    refetchInterval: isPipelineRunning ? 5000 : false,
  });

  // When pipeline is running, show "--" for stats of steps not yet completed
  const stepsCompleted = progress?.completed_steps ?? [];
  const pipelineActive = isPipelineRunning || progress?.status === "completed" || progress?.status === "failed" || progress?.status === "cancelled";

  const recordsFound = isPipelineRunning && !stepsCompleted.includes("search")
    ? "--" : (stats?.search?.total ?? 0);
  const afterDedup = isPipelineRunning && !stepsCompleted.includes("dedup")
    ? "--" : (stats?.dedup?.remaining ?? 0);
  const firstPassIncluded = isPipelineRunning && !stepsCompleted.includes("screen")
    ? "--" : (stats?.screen?.included ?? 0);
  const finalEligible = isPipelineRunning ? "--" : (stats?.eligibility?.included ?? 0);

  const handleRunAllClick = () => {
    if (isPipelineRunning) return;
    if (typeof recordsFound === "number" && recordsFound > 0) {
      setShowRunAllModal(true);
    } else {
      executeRunAll();
    }
  };

  const executeRunAll = async () => {
    try {
      await startPipeline();
      // Kick off polling immediately
      queryClient.invalidateQueries({ queryKey: ["pipeline-progress"] });
    } catch {
      // 409 = already running, ignore
    }
  };

  const handlePipelineFinished = useCallback(
    (status: PipelineStatusType) => {
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    [queryClient]
  );

  // Determine which step is currently active (for stepper highlighting)
  const activeStep = isPipelineRunning ? progress?.current_step : null;
  const completedInThisRun = isPipelineRunning ? (progress?.completed_steps ?? []) : null;

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold text-text-primary tracking-tight">
        Dashboard
      </h1>

      {/* Stat cards row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Records Found" value={isLoading ? "..." : recordsFound} color="blue" />
        <StatCard label="After Dedup" value={isLoading ? "..." : afterDedup} color="amber" />
        <StatCard label="First Pass Included" value={isLoading ? "..." : firstPassIncluded} color="green" />
        <StatCard label="Final Eligible" value={isLoading ? "..." : finalEligible} color="purple" />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* PRISMA Flow -- left column */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">PRISMA Flow</h2>
          <PrismaFlowDiagram stats={stats} />
        </div>

        {/* Pipeline -- right column */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">Pipeline</h2>
          <GlassCard className="flex flex-col gap-1">
            {/* Vertical stepper */}
            <div className="space-y-0">
              {PIPELINE_STEPS.map((step, idx) => {
                const count = getNestedValue(stats, step.statPath);
                // When pipeline is running, only mark steps completed in THIS run
                const isComplete = completedInThisRun
                  ? completedInThisRun.includes(step.key)
                  : count !== null && count > 0;
                const isActive = activeStep === step.key;

                return (
                  <div key={step.key} className="flex items-start gap-3 relative">
                    {/* Connector line */}
                    <div className="flex flex-col items-center">
                      {isActive ? (
                        <div className="w-[22px] h-[22px] rounded-full border-2 border-primary bg-primary/20 flex items-center justify-center">
                          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                        </div>
                      ) : isComplete ? (
                        <CheckCircle2 size={22} className="text-accent-green shrink-0" />
                      ) : (
                        <Circle size={22} className="text-text-muted shrink-0" />
                      )}
                      {idx < PIPELINE_STEPS.length - 1 && (
                        <div className="w-px h-8 bg-border-glass mt-1" />
                      )}
                    </div>

                    {/* Step content */}
                    <div className="pb-6">
                      <p
                        className={`text-sm font-medium ${
                          isActive
                            ? "text-primary"
                            : isComplete
                            ? "text-text-primary"
                            : "text-text-muted"
                        }`}
                      >
                        {step.label}
                        {isActive && (
                          <span className="ml-2 text-xs font-normal text-text-secondary">Running...</span>
                        )}
                      </p>
                      {count !== null && (isComplete || !completedInThisRun) && (
                        <p className="text-xs text-text-secondary mt-0.5">
                          {count.toLocaleString()} records
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pipeline progress bar (shows when running or just finished) */}
            <PipelineProgress onFinished={handlePipelineFinished} />

            {/* Run All / disabled button */}
            <button
              onClick={handleRunAllClick}
              disabled={isPipelineRunning}
              className={`mt-2 flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors cursor-pointer ${
                isPipelineRunning
                  ? "bg-text-muted/10 text-text-muted border border-text-muted/20 cursor-not-allowed"
                  : "bg-accent-green/15 text-accent-green border border-accent-green/20 hover:bg-accent-green/25"
              }`}
            >
              <Play size={16} />
              {isPipelineRunning ? "Pipeline Running..." : "Run All"}
            </button>
          </GlassCard>
        </div>
      </div>

      <Modal
        open={showRunAllModal}
        onClose={() => setShowRunAllModal(false)}
        onConfirm={executeRunAll}
        variant="danger"
        title="Re-run entire pipeline?"
        description={"This will re-run search, deduplication, and screening from scratch.\n\nYour existing screening and eligibility decisions will be overwritten. This may take several minutes."}
        confirmLabel="Yes, re-run pipeline"
        cancelLabel="Cancel"
      />
    </div>
  );
}
