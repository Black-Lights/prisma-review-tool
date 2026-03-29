"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Play, RefreshCw } from "lucide-react";
import StatCard from "@/components/StatCard";
import GlassCard from "@/components/GlassCard";
import { fetchStats, generateReport, runPipelineStep } from "@/lib/api";
import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PIPELINE_STEPS = [
  { key: "search", label: "Search Databases", statPath: "search.total" },
  { key: "dedup", label: "Deduplicate", statPath: "dedup.unique" },
  { key: "screen", label: "Keyword Screening", statPath: "screen.included" },
  { key: "eligibility", label: "AI Eligibility", statPath: "eligibility.included" },
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
  const [regenerating, setRegenerating] = useState(false);
  const [runningAll, setRunningAll] = useState(false);

  const { data: stats, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
  });

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await generateReport();
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    } finally {
      setRegenerating(false);
    }
  };

  const handleRunAll = async () => {
    setRunningAll(true);
    try {
      await runPipelineStep("run-all");
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    } finally {
      setRunningAll(false);
    }
  };

  const recordsFound = stats?.search?.total ?? 0;
  const afterDedup = stats?.dedup?.unique ?? 0;
  const firstPassIncluded = stats?.screen?.included ?? 0;
  const finalEligible = stats?.eligibility?.included ?? 0;

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
        {/* PRISMA Flow — left column */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">PRISMA Flow</h2>
          <GlassCard className="flex flex-col items-center gap-4">
            <img
              src={`${API_URL}/api/reports/prisma-flow`}
              alt="PRISMA 2020 flow diagram"
              className="w-full rounded-lg"
            />
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary-dim text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-50 transition-colors cursor-pointer"
            >
              <RefreshCw size={16} className={regenerating ? "animate-spin" : ""} />
              {regenerating ? "Regenerating..." : "Regenerate"}
            </button>
          </GlassCard>
        </div>

        {/* Pipeline — right column */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">Pipeline</h2>
          <GlassCard className="flex flex-col gap-1">
            {/* Vertical stepper */}
            <div className="space-y-0">
              {PIPELINE_STEPS.map((step, idx) => {
                const count = getNestedValue(stats, step.statPath);
                const isComplete = count !== null && count > 0;

                return (
                  <div key={step.key} className="flex items-start gap-3 relative">
                    {/* Connector line */}
                    <div className="flex flex-col items-center">
                      {isComplete ? (
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
                          isComplete ? "text-text-primary" : "text-text-muted"
                        }`}
                      >
                        {step.label}
                      </p>
                      {count !== null && (
                        <p className="text-xs text-text-secondary mt-0.5">
                          {count.toLocaleString()} records
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Run All button */}
            <button
              onClick={handleRunAll}
              disabled={runningAll}
              className="mt-2 flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg text-sm font-semibold bg-accent-green/15 text-accent-green border border-accent-green/20 hover:bg-accent-green/25 disabled:opacity-50 transition-colors cursor-pointer"
            >
              <Play size={16} />
              {runningAll ? "Running..." : "Run All"}
            </button>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
