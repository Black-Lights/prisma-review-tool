"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchConfig, updateConfig } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import {
  Settings,
  FolderOpen,
  Search,
  FileText,
  Filter,
  Key,
  Save,
  RotateCcw,
  X,
  Plus,
} from "lucide-react";

const SOURCES = ["arxiv", "openalex", "semantic_scholar", "scopus"] as const;

const SOURCE_INFO: Record<string, { label: string; note: string; reliable: boolean }> = {
  openalex: { label: "OpenAlex", note: "250M+ papers, most reliable", reliable: true },
  arxiv: { label: "arXiv", note: "Rate-limits aggressively, may return partial results", reliable: false },
  semantic_scholar: { label: "Semantic Scholar", note: "Heavy rate limits, often returns 0 results", reliable: false },
  scopus: { label: "Scopus", note: "Requires API key", reliable: true },
};

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
  });

  const [form, setForm] = useState<any>(null);
  const [includeInput, setIncludeInput] = useState("");
  const [excludeInput, setExcludeInput] = useState("");

  useEffect(() => {
    if (config && !form) {
      setForm(structuredClone(config));
    }
  }, [config, form]);

  const mutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["config"] }),
  });

  const handleReset = () => {
    if (config) setForm(structuredClone(config));
  };

  const handleSave = () => {
    if (form) mutation.mutate(form);
  };

  const updateField = (path: string[], value: any) => {
    setForm((prev: any) => {
      const next = structuredClone(prev);
      let obj = next;
      for (let i = 0; i < path.length - 1; i++) {
        obj = obj[path[i]];
      }
      obj[path[path.length - 1]] = value;
      return next;
    });
  };

  const addKeyword = (type: "include_keywords" | "exclude_keywords", value: string) => {
    if (!value.trim()) return;
    setForm((prev: any) => {
      const next = structuredClone(prev);
      if (!next.screening) next.screening = {};
      if (!next.screening.rules) next.screening.rules = {};
      const list = next.screening.rules[type] ?? [];
      if (!list.includes(value.trim())) {
        list.push(value.trim());
      }
      next.screening.rules[type] = list;
      return next;
    });
  };

  const removeKeyword = (type: "include_keywords" | "exclude_keywords", index: number) => {
    setForm((prev: any) => {
      const next = structuredClone(prev);
      next.screening.rules[type].splice(index, 1);
      return next;
    });
  };

  const toggleSource = (source: string) => {
    setForm((prev: any) => {
      const next = structuredClone(prev);
      const sources: string[] = next?.search?.sources ?? [];
      const idx = sources.indexOf(source);
      if (idx >= 0) sources.splice(idx, 1);
      else sources.push(source);
      if (!next.search) next.search = {};
      next.search.sources = sources;
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!form) return null;

  return (
    <div className="space-y-8">
      <div data-tutorial="settings-header" className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border-glass text-text-secondary hover:border-border-glass-hover hover:text-text-primary"
          >
            <RotateCcw className="w-4 h-4" />
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={mutation.isPending}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary text-bg-base font-semibold hover:opacity-90 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {mutation.isPending ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </div>

      {mutation.isSuccess && (
        <div className="glass p-3 border-l-4 border-l-accent-green text-accent-green text-sm">
          Configuration saved successfully.
        </div>
      )}

      {/* Project */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <FolderOpen className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Project</h2>
        </div>
        <label className="block text-sm text-text-secondary mb-1">Project Name</label>
        <input
          type="text"
          value={form?.project?.name ?? ""}
          onChange={(e) => updateField(["project", "name"], e.target.value)}
          className="glass-input w-full max-w-md"
          placeholder="My Literature Review"
        />
      </GlassCard>

      {/* Search */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Search className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Search</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div>
            <label className="block text-sm text-text-secondary mb-1">Start Date</label>
            <input
              type="date"
              value={form?.search?.date_range?.start ?? ""}
              onChange={(e) => updateField(["search", "date_range", "start"], e.target.value)}
              className="glass-input w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1">End Date</label>
            <input
              type="date"
              value={form?.search?.date_range?.end ?? ""}
              onChange={(e) => updateField(["search", "date_range", "end"], e.target.value)}
              className="glass-input w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1">Max Results per Query</label>
            <input
              type="number"
              value={form?.search?.max_results_per_query ?? 100}
              onChange={(e) => updateField(["search", "max_results_per_query"], parseInt(e.target.value) || 0)}
              className="glass-input w-full"
              min={1}
            />
          </div>
        </div>
        <div>
          <label className="block text-sm text-text-secondary mb-2">Sources</label>
          <div className="space-y-2">
            {SOURCES.map((source) => {
              const info = SOURCE_INFO[source];
              const checked = (form?.search?.sources ?? []).includes(source);
              return (
                <label key={source} className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSource(source)}
                    className="w-4 h-4 accent-primary rounded shrink-0"
                  />
                  <span className="text-sm">
                    <span className="text-text-primary font-medium">{info?.label ?? source}</span>
                    {info?.note && (
                      <span className={`ml-1.5 text-xs ${info.reliable ? "text-text-muted" : "text-accent-amber"}`}>
                        — {info.note}
                      </span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </GlassCard>

      {/* Search Queries */}
      <GlassCard data-tutorial="search-queries">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Search Queries</h2>
          </div>
          <div className="relative group">
            <button className="flex items-center justify-center w-7 h-7 rounded-full bg-primary/10 text-primary hover:bg-primary/20 text-sm font-bold">
              i
            </button>
            <div className="absolute right-0 top-9 w-80 glass-elevated p-4 rounded-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible z-50 text-sm space-y-2 shadow-xl">
              <p className="font-semibold text-text-primary">How to write queries</p>
              <ul className="text-text-secondary space-y-1.5 list-none">
                <li><span className="text-primary font-mono text-xs">OR</span> — between synonyms: <span className="text-text-muted font-mono text-xs">&quot;crop&quot; OR &quot;agriculture&quot;</span></li>
                <li><span className="text-primary font-mono text-xs">AND</span> — between concepts: <span className="text-text-muted font-mono text-xs">&quot;deep learning&quot; AND &quot;remote sensing&quot;</span></li>
                <li><span className="text-primary font-mono text-xs">&quot;...&quot;</span> — exact phrase: <span className="text-text-muted font-mono text-xs">&quot;foundation model&quot;</span></li>
                <li><span className="text-primary font-mono text-xs">( )</span> — grouping: <span className="text-text-muted font-mono text-xs">(&quot;A&quot; OR &quot;B&quot;) AND &quot;C&quot;</span></li>
              </ul>
              <p className="text-text-muted pt-1 border-t border-border-glass">Each query is sent to all selected databases. Use 3-5 focused queries rather than one large query.</p>
            </div>
          </div>
        </div>

        {/* Query cards */}
        <div className="space-y-4">
          {(Array.isArray(form?.search?.queries) ? form.search.queries : []).map((q: any, idx: number) => (
            <div key={idx} className="glass p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-md bg-primary/15 text-primary text-xs font-bold">{idx + 1}</span>
                  <input
                    type="text"
                    value={q.name || ""}
                    onChange={(e) => {
                      setForm((prev: any) => {
                        const next = structuredClone(prev);
                        next.search.queries[idx].name = e.target.value;
                        return next;
                      });
                    }}
                    className="glass-input py-1 px-2 text-sm font-medium w-80"
                    placeholder="Query name"
                  />
                </div>
                <button
                  onClick={() => {
                    setForm((prev: any) => {
                      const next = structuredClone(prev);
                      next.search.queries.splice(idx, 1);
                      return next;
                    });
                  }}
                  className="text-text-muted hover:text-accent-red p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <textarea
                value={q.terms || ""}
                onChange={(e) => {
                  setForm((prev: any) => {
                    const next = structuredClone(prev);
                    next.search.queries[idx].terms = e.target.value;
                    return next;
                  });
                }}
                rows={3}
                className="glass-input w-full font-mono text-sm leading-relaxed resize-y"
                placeholder={'("term A" OR "term B") AND ("method") AND ("domain")'}
              />
            </div>
          ))}
        </div>

        <button
          onClick={() => {
            setForm((prev: any) => {
              const next = structuredClone(prev);
              if (!next.search) next.search = {};
              if (!next.search.queries) next.search.queries = [];
              next.search.queries.push({ name: `query_${next.search.queries.length + 1}`, terms: "" });
              return next;
            });
          }}
          className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg border border-dashed border-border-glass-hover text-text-secondary hover:text-primary hover:border-primary/30"
        >
          <Plus className="w-4 h-4" />
          Add Query
        </button>
      </GlassCard>

      {/* Screening Rules */}
      <GlassCard data-tutorial="screening-rules">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Screening Rules</h2>
          </div>
          <div className="relative group">
            <button className="flex items-center justify-center w-7 h-7 rounded-full bg-primary/10 text-primary hover:bg-primary/20 text-sm font-bold">
              i
            </button>
            <div className="absolute right-0 top-9 w-80 glass-elevated p-4 rounded-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible z-50 text-sm space-y-2 shadow-xl">
              <p className="font-semibold text-text-primary">How screening works</p>
              <ul className="text-text-secondary space-y-1.5 list-none">
                <li><span className="text-accent-green font-semibold">Include</span> — paper matches ≥ minimum threshold of include keywords AND 0 exclude keywords</li>
                <li><span className="text-accent-red font-semibold">Exclude</span> — paper matches any exclude keyword</li>
                <li><span className="text-accent-amber font-semibold">Maybe</span> — not enough include keywords, no exclude match</li>
              </ul>
              <p className="text-text-muted pt-1 border-t border-border-glass">Example: with threshold=4 and 12 include keywords, a paper must mention at least 4 of them in title+abstract to be included.</p>
            </div>
          </div>
        </div>

        {/* Include Keywords */}
        <div className="mb-6">
          <label className="block text-sm text-text-secondary mb-2">Include Keywords</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {(form?.screening?.rules?.include_keywords ?? []).map((kw: string, i: number) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-primary-dim text-primary border border-primary/20"
              >
                {kw}
                <button
                  onClick={() => removeKeyword("include_keywords", i)}
                  className="hover:text-text-primary"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 max-w-md">
            <input
              type="text"
              value={includeInput}
              onChange={(e) => setIncludeInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addKeyword("include_keywords", includeInput);
                  setIncludeInput("");
                }
              }}
              className="glass-input flex-1"
              placeholder='e.g. "foundation model", "remote sensing"'
            />
            <button
              onClick={() => {
                addKeyword("include_keywords", includeInput);
                setIncludeInput("");
              }}
              className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border-glass text-primary hover:border-primary/30"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Exclude Keywords */}
        <div className="mb-6">
          <label className="block text-sm text-text-secondary mb-2">Exclude Keywords</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {(form?.screening?.rules?.exclude_keywords ?? []).map((kw: string, i: number) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-accent-red/15 text-accent-red border border-accent-red/20"
              >
                {kw}
                <button
                  onClick={() => removeKeyword("exclude_keywords", i)}
                  className="hover:text-text-primary"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 max-w-md">
            <input
              type="text"
              value={excludeInput}
              onChange={(e) => setExcludeInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addKeyword("exclude_keywords", excludeInput);
                  setExcludeInput("");
                }
              }}
              className="glass-input flex-1"
              placeholder='e.g. "medical imaging", "urban", "flood"'
            />
            <button
              onClick={() => {
                addKeyword("exclude_keywords", excludeInput);
                setExcludeInput("");
              }}
              className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border-glass text-accent-red hover:border-accent-red/30"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Min Include Hits */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="block text-sm text-text-secondary">
              Minimum Include Keyword Hits
            </label>
            <div className="relative group">
              <button className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 text-[10px] font-bold">
                i
              </button>
              <div className="absolute left-0 bottom-7 w-72 glass-elevated p-3 rounded-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible z-50 text-xs space-y-1.5 shadow-xl">
                <p className="text-text-primary font-medium">How many include keywords must appear in a paper&apos;s title+abstract for it to pass.</p>
                <p className="text-text-muted">Low (1-2) = permissive, many papers pass</p>
                <p className="text-text-muted">High (4-5) = strict, only highly relevant papers</p>
                <p className="text-accent-amber">Tip: Start with 2, check results, increase if too many pass.</p>
              </div>
            </div>
          </div>
          <input
            type="number"
            value={form?.screening?.rules?.min_include_hits ?? 2}
            onChange={(e) =>
              updateField(["screening", "rules", "min_include_hits"], parseInt(e.target.value) || 1)
            }
            className="glass-input w-32"
            min={1}
            max={10}
          />
        </div>
      </GlassCard>

      {/* API Keys */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">API Keys</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-text-secondary mb-1">OpenAlex Email (optional, for faster API access)</label>
            <input
              type="text"
              value={form?.api_keys?.openalex_email ?? ""}
              onChange={(e) => updateField(["api_keys", "openalex_email"], e.target.value)}
              className="glass-input w-full"
              placeholder="your@email.com"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1">Scopus API Key (optional, needs institutional access)</label>
            <input
              type="password"
              value={form?.api_keys?.scopus ?? ""}
              onChange={(e) => updateField(["api_keys", "scopus"], e.target.value)}
              className="glass-input w-full"
              placeholder="Enter Scopus API key"
            />
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
