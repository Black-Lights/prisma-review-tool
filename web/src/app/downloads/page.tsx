"use client";

import { Suspense, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { downloadPapers, fetchDownloadLog, type DownloadEntry } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import StatCard from "@/components/StatCard";
import {
  Download,
  Loader2,
  CheckCircle,
  XCircle,
  Info,
  FileText,
  ExternalLink,
  Eye,
  AlertTriangle,
} from "lucide-react";
import { usePersistedFilters } from "@/hooks/usePersistedFilters";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ViewFilter = "all" | "downloaded" | "no_oa" | "failed";

const DOWNLOADS_DEFAULTS = { filter: "all" } as const;

export default function DownloadsPage() {
  return (
    <Suspense>
      <DownloadsContent />
    </Suspense>
  );
}

function DownloadsContent() {
  const queryClient = useQueryClient();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { filters, setFilter: setPersistedFilter } = usePersistedFilters("downloads", DOWNLOADS_DEFAULTS);
  const viewFilter = filters.filter as ViewFilter;
  const setViewFilter = (v: ViewFilter) => setPersistedFilter("filter", v);

  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const { data: log } = useQuery({
    queryKey: ["download-log"],
    queryFn: fetchDownloadLog,
  });

  const handleDownload = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await downloadPapers();
      queryClient.invalidateQueries({ queryKey: ["download-log"] });
    } catch (e: any) {
      setError(e.message || "Download failed");
    } finally {
      setIsLoading(false);
    }
  };

  const openPreview = (filename: string) => {
    setPreviewFile(filename);
    // Use same-origin Next.js API proxy to avoid cross-origin issues
    setPreviewUrl(`/api/pdf/${encodeURIComponent(filename)}`);
  };

  const closePreview = () => {
    setPreviewFile(null);
    setPreviewUrl(null);
  };

  const hasDownloads = (log?.total ?? 0) > 0;

  const filteredPapers = (log?.papers ?? []).filter((p) => {
    if (viewFilter === "all") return true;
    if (viewFilter === "downloaded") return p.status === "downloaded" || p.status === "exists";
    return p.status === viewFilter;
  });

  const isAvailable = (status: string) => status === "downloaded" || status === "exists";

  const statusIcon = (status: string) => {
    if (isAvailable(status)) return <CheckCircle size={14} className="text-accent-green" />;
    switch (status) {
      case "no_oa": return <AlertTriangle size={14} className="text-accent-amber" />;
      case "failed": return <XCircle size={14} className="text-accent-red" />;
      default: return null;
    }
  };

  const statusLabel = (status: string) => {
    if (isAvailable(status)) return "Downloaded";
    switch (status) {
      case "no_oa": return "No Open Access";
      case "failed": return "Failed";
      default: return status;
    }
  };

  return (
    <div className="space-y-6">
      <div data-tutorial="downloads-header" className="flex items-center gap-3">
        <Download className="w-7 h-7 text-primary" />
        <h1 className="text-2xl font-bold text-text-primary">Downloads</h1>
      </div>

      {/* Action + Stats row */}
      <div className="flex flex-wrap items-center gap-4">
        <button
          onClick={handleDownload}
          disabled={isLoading}
          className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-primary text-bg-base font-semibold hover:opacity-90 disabled:opacity-50 cursor-pointer"
        >
          {isLoading ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Downloading...</>
          ) : (
            <><Download className="w-4 h-4" /> {hasDownloads ? "Re-download" : "Start Download"}</>
          )}
        </button>

        {hasDownloads && (
          <div className="flex gap-3 text-sm">
            <span className="text-accent-green">{log?.downloaded ?? 0} downloaded</span>
            <span className="text-text-muted">|</span>
            <span className="text-accent-amber">{log?.no_oa ?? 0} no OA</span>
            <span className="text-text-muted">|</span>
            <span className="text-accent-red">{log?.failed ?? 0} failed</span>
          </div>
        )}
      </div>

      {error && (
        <div className="glass p-4 border-l-4 border-l-accent-red text-accent-red flex items-center gap-2">
          <XCircle className="w-5 h-5 shrink-0" /> {error}
        </div>
      )}

      {/* PDF Viewer */}
      {previewFile && (
        <GlassCard className="!p-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border-glass">
            <span className="text-sm text-text-primary font-medium truncate">{previewFile}</span>
            <div className="flex items-center gap-2">
              {previewUrl && (
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline flex items-center gap-1"
                >
                  Open in new tab <ExternalLink size={12} />
                </a>
              )}
              <button
                onClick={closePreview}
                className="text-xs text-text-muted hover:text-text-primary px-2 py-1 cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
          {previewUrl ? (
            <iframe
              src={previewUrl}
              className="w-full bg-white"
              style={{ height: "70vh" }}
              title="PDF Preview"
            />
          ) : (
            <div className="flex items-center justify-center py-12 text-text-muted text-sm">
              Loading PDF...
            </div>
          )}
        </GlassCard>
      )}

      {/* Papers list */}
      {hasDownloads && (
        <>
          {/* Filter pills */}
          <div className="flex gap-2">
            {(["all", "downloaded", "no_oa", "failed"] as ViewFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setViewFilter(f)}
                className={`px-4 py-1.5 rounded-full text-xs font-medium border transition-colors cursor-pointer ${
                  viewFilter === f
                    ? "bg-primary/15 text-primary border-primary/30"
                    : "bg-bg-glass text-text-secondary border-border-glass hover:border-border-glass-hover"
                }`}
              >
                {f === "all" ? `All (${log?.total})` :
                 f === "downloaded" ? `Downloaded (${log?.downloaded})` :
                 f === "no_oa" ? `No OA (${log?.no_oa})` :
                 `Failed (${log?.failed})`}
              </button>
            ))}
          </div>

          {/* Table */}
          <GlassCard data-tutorial="downloads-table" className="!p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-glass text-left text-text-muted">
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">DOI</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredPapers.map((paper, i) => (
                  <tr key={paper.id} className={`border-b border-border-glass/50 hover:bg-bg-glass/40 ${i % 2 === 1 ? "bg-bg-glass/20" : ""}`}>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-1.5 text-xs">
                        {statusIcon(paper.status)}
                        {statusLabel(paper.status)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 max-w-md">
                      <span className="text-text-primary line-clamp-1">{paper.title}</span>
                    </td>
                    <td className="px-4 py-2.5 text-text-muted text-xs">
                      {paper.doi ? (
                        <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                          {paper.doi}
                        </a>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {isAvailable(paper.status) && paper.file && (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openPreview(paper.file!)}
                            className="flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer"
                          >
                            <Eye size={13} /> View
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>
        </>
      )}

      {!hasDownloads && (
        <GlassCard className="text-center py-10">
          <div className="flex flex-col items-center gap-3">
            <div className="w-14 h-14 rounded-full bg-primary-dim flex items-center justify-center">
              <Download className="w-7 h-7 text-primary" />
            </div>
            <p className="text-text-secondary max-w-lg">
              Download open access PDFs for eligible papers. Click "Start Download" to begin.
            </p>
          </div>
        </GlassCard>
      )}

      <div className="flex items-start gap-3 glass p-4 border border-border-glass">
        <Info className="w-5 h-5 text-primary shrink-0 mt-0.5" />
        <p className="text-sm text-text-secondary">
          Papers without open access can be downloaded via your institutional library.
          Check your university portal for access to subscription-based journals.
        </p>
      </div>
    </div>
  );
}
