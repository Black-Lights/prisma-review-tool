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
      const list = next?.screening_rules?.[type] ?? [];
      if (!list.includes(value.trim())) {
        list.push(value.trim());
      }
      if (!next.screening_rules) next.screening_rules = {};
      next.screening_rules[type] = list;
      return next;
    });
  };

  const removeKeyword = (type: "include_keywords" | "exclude_keywords", index: number) => {
    setForm((prev: any) => {
      const next = structuredClone(prev);
      next.screening_rules[type].splice(index, 1);
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

  const queriesYaml = form?.search?.queries
    ? typeof form.search.queries === "string"
      ? form.search.queries
      : Array.isArray(form.search.queries)
        ? form.search.queries.map((q: any) =>
            typeof q === "string" ? `- "${q}"` : `- terms: ${JSON.stringify(q.terms)}\n  boolean: "${q.boolean || ""}"`
          ).join("\n")
        : ""
    : "";

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
      <div className="flex items-center justify-between">
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
          value={form?.project ?? ""}
          onChange={(e) => updateField(["project"], e.target.value)}
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
              value={form?.search?.start_date ?? ""}
              onChange={(e) => updateField(["search", "start_date"], e.target.value)}
              className="glass-input w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1">End Date</label>
            <input
              type="date"
              value={form?.search?.end_date ?? ""}
              onChange={(e) => updateField(["search", "end_date"], e.target.value)}
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
          <div className="flex flex-wrap gap-3">
            {SOURCES.map((source) => (
              <label key={source} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(form?.search?.sources ?? []).includes(source)}
                  onChange={() => toggleSource(source)}
                  className="w-4 h-4 accent-primary rounded"
                />
                <span className="text-sm text-text-primary">{source.replace("_", " ")}</span>
              </label>
            ))}
          </div>
        </div>
      </GlassCard>

      {/* Search Queries */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <FileText className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Search Queries</h2>
        </div>
        <p className="text-sm text-text-muted mb-3">
          Edit queries in YAML format. Each entry defines a search query sent to the selected sources.
        </p>
        <textarea
          value={queriesYaml}
          onChange={(e) => updateField(["search", "queries"], e.target.value)}
          rows={10}
          className="glass-input w-full font-mono text-sm leading-relaxed resize-y"
          placeholder={'- "geospatial foundation models"\n- terms: ["remote sensing", "pre-training"]\n  boolean: "AND"'}
        />
      </GlassCard>

      {/* Screening Rules */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Screening Rules</h2>
        </div>

        {/* Include Keywords */}
        <div className="mb-6">
          <label className="block text-sm text-text-secondary mb-2">Include Keywords</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {(form?.screening_rules?.include_keywords ?? []).map((kw: string, i: number) => (
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
                  addKeyword("include_keywords", includeInput);
                  setIncludeInput("");
                }
              }}
              className="glass-input flex-1"
              placeholder="Add include keyword..."
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
            {(form?.screening_rules?.exclude_keywords ?? []).map((kw: string, i: number) => (
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
                  addKeyword("exclude_keywords", excludeInput);
                  setExcludeInput("");
                }
              }}
              className="glass-input flex-1"
              placeholder="Add exclude keyword..."
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
          <label className="block text-sm text-text-secondary mb-1">
            Minimum Include Keyword Hits
          </label>
          <input
            type="number"
            value={form?.screening_rules?.min_include_hits ?? 1}
            onChange={(e) =>
              updateField(["screening_rules", "min_include_hits"], parseInt(e.target.value) || 0)
            }
            className="glass-input w-32"
            min={0}
          />
          <p className="text-xs text-text-muted mt-1">
            Papers must match at least this many include keywords to pass screening.
          </p>
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
            <label className="block text-sm text-text-secondary mb-1">OpenAlex Email</label>
            <input
              type="text"
              value={form?.api_keys?.openalex_email ?? ""}
              onChange={(e) => updateField(["api_keys", "openalex_email"], e.target.value)}
              className="glass-input w-full"
              placeholder="your@email.com"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1">Scopus API Key</label>
            <input
              type="password"
              value={form?.api_keys?.scopus_key ?? ""}
              onChange={(e) => updateField(["api_keys", "scopus_key"], e.target.value)}
              className="glass-input w-full"
              placeholder="Enter Scopus API key"
            />
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
