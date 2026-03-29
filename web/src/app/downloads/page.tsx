"use client";

import { useState } from "react";
import { downloadPapers } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import StatCard from "@/components/StatCard";
import {
  Download,
  Loader2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Info,
} from "lucide-react";

interface DownloadResult {
  downloaded?: number;
  no_open_access?: number;
  failed?: number;
}

export default function DownloadsPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<DownloadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await downloadPapers();
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Download failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <Download className="w-7 h-7 text-primary" />
        <h1 className="text-2xl font-bold text-text-primary">Downloads</h1>
      </div>

      {/* Action Card */}
      <GlassCard className="text-center py-10">
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-primary-dim flex items-center justify-center">
            <Download className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-text-primary">
            Download Open Access PDFs
          </h2>
          <p className="text-text-secondary max-w-lg">
            Automatically download PDFs for all eligible papers that have open access versions
            available. Papers are saved to the project downloads folder.
          </p>
          <button
            onClick={handleDownload}
            disabled={isLoading}
            className="flex items-center gap-2 px-8 py-3 rounded-lg bg-primary text-bg-base font-semibold text-lg hover:opacity-90 disabled:opacity-50 mt-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Downloading...
              </>
            ) : (
              <>
                <Download className="w-5 h-5" />
                Start Download
              </>
            )}
          </button>
        </div>
      </GlassCard>

      {/* Error */}
      {error && (
        <div className="glass p-4 border-l-4 border-l-accent-red text-accent-red flex items-center gap-2">
          <XCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-accent-green" />
            Download Complete
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StatCard
              label="Downloaded"
              value={result.downloaded ?? 0}
              color="green"
            />
            <StatCard
              label="No Open Access"
              value={result.no_open_access ?? 0}
              color="amber"
            />
            <StatCard
              label="Failed"
              value={result.failed ?? 0}
              color="red"
            />
          </div>
        </div>
      )}

      {/* Info note */}
      <div className="flex items-start gap-3 glass p-4 border border-border-glass">
        <Info className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
        <p className="text-sm text-text-secondary">
          Papers without open access can be downloaded via your institutional library.
          Check your university portal for access to subscription-based journals.
        </p>
      </div>
    </div>
  );
}
