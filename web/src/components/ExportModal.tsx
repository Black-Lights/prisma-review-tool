"use client";

import { useState, useEffect, useRef } from "react";
import { X, Download, FileText, FileSpreadsheet } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ─── Field definitions ─────────────────────────────────────────────────── */

interface FieldDef {
  key: string;
  label: string;
  defaultOn: boolean;
  /** field is unavailable when source filter matches */
  unavailableWhen?: string;
  unavailableReason?: string;
}

interface FieldGroup {
  label: string;
  fields: FieldDef[];
}

const FIELD_GROUPS: FieldGroup[] = [
  {
    label: "Citation information",
    fields: [
      { key: "title", label: "Title", defaultOn: true },
      { key: "authors", label: "Author(s)", defaultOn: true },
      { key: "year", label: "Year", defaultOn: true },
      { key: "doi", label: "DOI", defaultOn: true },
      { key: "url", label: "URL", defaultOn: true },
      { key: "venue", label: "Venue / Journal", defaultOn: true },
      { key: "source", label: "Source database", defaultOn: true },
      { key: "source_id", label: "Source ID (EID)", defaultOn: false },
      { key: "bibtex_key", label: "BibTeX key", defaultOn: true },
    ],
  },
  {
    label: "Abstract & Keywords",
    fields: [
      { key: "abstract", label: "Abstract", defaultOn: false },
      {
        key: "keywords",
        label: "Author keywords",
        defaultOn: false,
        unavailableWhen: "semantic_scholar",
        unavailableReason: "Not provided by Semantic Scholar",
      },
    ],
  },
  {
    label: "Screening information",
    fields: [
      { key: "screen_decision", label: "Decision (1st pass)", defaultOn: false },
      { key: "screen_reason", label: "Reason (1st pass)", defaultOn: false },
      { key: "screen_method", label: "Method (1st pass)", defaultOn: false },
      { key: "eligibility_decision", label: "Eligibility decision", defaultOn: false },
      { key: "eligibility_reason", label: "Eligibility reason", defaultOn: false },
      { key: "eligibility_method", label: "Eligibility method", defaultOn: false },
    ],
  },
];

/* ─── Props ──────────────────────────────────────────────────────────────── */

interface ExportModalProps {
  open: boolean;
  onClose: () => void;
  format: "csv" | "bib";
  totalPapers: number;
  decisionFilter: string;
  sourceFilter: string;
}

/* ─── Component ──────────────────────────────────────────────────────────── */

export default function ExportModal({
  open,
  onClose,
  format,
  totalPapers,
  decisionFilter,
  sourceFilter,
}: ExportModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Build initial selected fields from defaults
  const [selected, setSelected] = useState<Set<string>>(() => {
    const s = new Set<string>();
    for (const g of FIELD_GROUPS) {
      for (const f of g.fields) {
        if (f.defaultOn) s.add(f.key);
      }
    }
    return s;
  });

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  const isUnavailable = (f: FieldDef) =>
    f.unavailableWhen != null && sourceFilter === f.unavailableWhen;

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleGroup = (group: FieldGroup) => {
    const available = group.fields.filter((f) => !isUnavailable(f));
    const allOn = available.every((f) => selected.has(f.key));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const f of available) {
        if (allOn) next.delete(f.key);
        else next.add(f.key);
      }
      return next;
    });
  };

  const selectAll = () => {
    const all = new Set<string>();
    for (const g of FIELD_GROUPS) {
      for (const f of g.fields) {
        if (!isUnavailable(f)) all.add(f.key);
      }
    }
    setSelected(all);
  };

  const groupChecked = (group: FieldGroup) => {
    const available = group.fields.filter((f) => !isUnavailable(f));
    if (available.length === 0) return false;
    return available.every((f) => selected.has(f.key));
  };

  const groupIndeterminate = (group: FieldGroup) => {
    const available = group.fields.filter((f) => !isUnavailable(f));
    const count = available.filter((f) => selected.has(f.key)).length;
    return count > 0 && count < available.length;
  };

  const handleExport = () => {
    const params = new URLSearchParams();
    if (decisionFilter !== "all") params.set("decision", decisionFilter);
    if (sourceFilter !== "all") params.set("source", sourceFilter);
    if (format === "csv" && selected.size > 0) {
      params.set("fields", Array.from(selected).join(","));
    }
    const qs = params.toString();
    const url = `${API}/api/papers/export/${format}${qs ? `?${qs}` : ""}`;
    window.open(url, "_blank");
    onClose();
  };

  const isCsv = format === "csv";
  const FormatIcon = isCsv ? FileSpreadsheet : FileText;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[100] flex items-center justify-center"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      <div className="relative glass-elevated p-0 w-full max-w-xl mx-4 shadow-2xl animate-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-6 pb-2">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
              <FormatIcon size={22} />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-text-primary">
                Export {totalPapers.toLocaleString()} papers to {format.toUpperCase()}
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                {decisionFilter !== "all" || sourceFilter !== "all"
                  ? `Filtered: ${decisionFilter !== "all" ? decisionFilter.replace("_", " ") : "all decisions"}, ${sourceFilter !== "all" ? sourceFilter : "all sources"}`
                  : "All papers (no filters applied)"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-bg-glass"
          >
            <X size={18} />
          </button>
        </div>

        {/* Field picker (CSV only) */}
        {isCsv ? (
          <div className="px-6 py-4">
            <p className="text-sm text-text-secondary mb-4">
              What information do you want to export?
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-4">
              {FIELD_GROUPS.map((group) => (
                <div key={group.label}>
                  {/* Group header */}
                  <label className="flex items-center gap-2 cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={groupChecked(group)}
                      ref={(el) => {
                        if (el) el.indeterminate = groupIndeterminate(group);
                      }}
                      onChange={() => toggleGroup(group)}
                      className="accent-primary w-3.5 h-3.5"
                    />
                    <span className="text-sm font-semibold text-text-primary">
                      {group.label}
                    </span>
                  </label>
                  {/* Fields */}
                  <div className="space-y-1.5 pl-1">
                    {group.fields.map((f) => {
                      const unavail = isUnavailable(f);
                      return (
                        <label
                          key={f.key}
                          className={`flex items-center gap-2 ${
                            unavail
                              ? "opacity-40 cursor-not-allowed"
                              : "cursor-pointer"
                          }`}
                          title={unavail ? f.unavailableReason : undefined}
                        >
                          <input
                            type="checkbox"
                            checked={!unavail && selected.has(f.key)}
                            disabled={unavail}
                            onChange={() => toggle(f.key)}
                            className="accent-primary w-3.5 h-3.5"
                          />
                          <span className="text-xs text-text-secondary">
                            {f.label}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="px-6 py-4">
            <p className="text-sm text-text-secondary">
              BibTeX export includes: title, authors, year, DOI, URL, journal/venue, and abstract.
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border-glass">
          <div>
            {isCsv && (
              <button
                onClick={selectAll}
                className="text-xs text-primary hover:underline"
              >
                Select all information
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary bg-bg-glass border border-border-glass hover:bg-bg-elevated hover:text-text-primary"
            >
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={isCsv && selected.size === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary/80 hover:bg-primary text-bg-base disabled:opacity-50"
            >
              <Download size={15} />
              Export
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .animate-in {
          animation: modalIn 0.2s ease-out;
        }
        @keyframes modalIn {
          from {
            opacity: 0;
            transform: scale(0.95) translateY(8px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
