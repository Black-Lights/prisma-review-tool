"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchActiveProject,
  fetchConfig,
  fetchConfigReadiness,
  updateConfig,
  type ConfigData,
} from "@/lib/api";
import {
  SECRET_MASK,
  configConflict,
  maskSecrets,
  savePayload,
  secretDisplayValue,
  secretInputValue,
  secretState,
  splitDocTypes,
  type ConfigConflict,
} from "@/lib/configForm";
import { isIssn, normalizeVenue } from "@/lib/venues";
import GlassCard from "@/components/GlassCard";
import {
  Settings,
  FolderOpen,
  Search,
  FileText,
  Filter,
  SlidersHorizontal,
  Key,
  Save,
  RotateCcw,
  X,
  Plus,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";

const SOURCES = ["arxiv", "crossref", "openalex", "semantic_scholar", "scopus"] as const;

// Canonical document types the backend (search.filters) knows how to map per
// source. Keep in sync with prisma_review/search/filters.py (_DOC_TYPE_MAP)
// and KNOWN_DOCUMENT_TYPES in prisma_review/config.py.
const DOC_TYPES = [
  "journal-article",
  "review",
  "conference-paper",
  "book-chapter",
  "preprint",
] as const;

const SOURCE_INFO: Record<string, { label: string; note: string; reliable: boolean }> = {
  arxiv: { label: "arXiv", note: "Rate-limits aggressively, may return partial results", reliable: false },
  crossref: { label: "Crossref", note: "150M+ records, free, no API key", reliable: true },
  openalex: { label: "OpenAlex", note: "250M+ papers; a free API key is strongly recommended", reliable: true },
  semantic_scholar: { label: "Semantic Scholar", note: "Boolean search, but heavy rate limits; a query that stops early is reported", reliable: false },
  scopus: { label: "Scopus", note: "Requires API key", reliable: true },
};

type KeywordList = "include_keywords" | "exclude_keywords" | "required_keywords";

// Nested sections created on first edit (the API omits empty ones).
const searchOf = (c: ConfigData) => (c.search ??= {});
const filtersOf = (c: ConfigData) => (searchOf(c).filters ??= {});
const rulesOf = (c: ConfigData) => ((c.screening ??= {}).rules ??= {});
const keysOf = (c: ConfigData) => (c.api_keys ??= {});

export default function SettingsPage() {
  const { data: activeProject, isLoading: projectLoading } = useQuery({
    queryKey: ["active-project"],
    queryFn: fetchActiveProject,
  });
  const { data: config, isLoading, error } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
  });

  if (isLoading || projectLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!config) {
    return (
      <GlassCard className="border-l-4 border-l-accent-red">
        <p className="text-sm text-accent-red">Could not load the configuration.</p>
        {error && <p className="text-sm text-text-secondary mt-1">{error.message}</p>}
      </GlassCard>
    );
  }

  // The form belongs to one project: when the active project changes (here,
  // in another tab or through the MCP server) it is rebuilt from scratch, so
  // edits made for one project can never be saved into another (WEB#3).
  const project = activeProject?.active ?? "";
  return (
    <SettingsForm
      key={project}
      project={project}
      projectLabel={activeProject?.display_name || project}
      config={config}
    />
  );
}

function SettingsForm({
  project,
  projectLabel,
  config,
}: {
  project: string;
  projectLabel: string;
  config: ConfigData;
}) {
  const queryClient = useQueryClient();

  // null while the form is clean: it then simply shows the server config and
  // follows every refetch. The first edit takes a copy (the draft) and records
  // the _version it was based on, which is sent back on save.
  const [draft, setDraft] = useState<ConfigData | null>(null);
  const [baseVersion, setBaseVersion] = useState<string | null>(null);
  const [conflict, setConflict] = useState<ConfigConflict | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [includeInput, setIncludeInput] = useState("");
  const [excludeInput, setExcludeInput] = useState("");
  const [requiredInput, setRequiredInput] = useState("");
  const [venuesInput, setVenuesInput] = useState("");

  const form: ConfigData = draft ?? config;
  const dirty = draft !== null;
  const serverVersion = config._version ?? null;
  // The file changed on disk (and was refetched) after editing started.
  const changedOnDisk = dirty && baseVersion !== serverVersion;

  const { data: readiness } = useQuery({
    queryKey: ["config-readiness"],
    queryFn: fetchConfigReadiness,
  });

  // Ask before closing or reloading the tab with unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const edit = (fn: (next: ConfigData) => void) => {
    if (draft === null) setBaseVersion(serverVersion);
    setSaved(false);
    setSaveError(null);
    setDraft((prev) => {
      const next = structuredClone(prev ?? config);
      fn(next);
      return next;
    });
  };

  const discard = () => {
    setDraft(null);
    setBaseVersion(null);
    setConflict(null);
    setSaveError(null);
    queryClient.invalidateQueries({ queryKey: ["config"] });
    // Re-keys the form if the active project changed meanwhile.
    queryClient.invalidateQueries({ queryKey: ["active-project"] });
  };

  const mutation = useMutation({
    mutationFn: async ({ data, version }: { data: ConfigData; version: string | null }) => {
      // Not through the query cache: a changed project re-keys this form,
      // which would drop the edits before the user sees why.
      const active = await fetchActiveProject();
      if ((active.active ?? "") !== project) {
        throw new Error(
          `The active project changed to "${active.display_name || active.active || "none"}" while you were ` +
            `editing "${projectLabel}". Your edits were not saved. Discard them to load the new project's settings.`,
        );
      }
      return updateConfig(savePayload(data, version));
    },
    onSuccess: (res, { data }) => {
      queryClient.setQueryData<ConfigData>(["config"], { ...maskSecrets(data), _version: res._version });
      setDraft(null);
      setBaseVersion(null);
      setConflict(null);
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.invalidateQueries({ queryKey: ["config-readiness"] });
      queryClient.invalidateQueries({ queryKey: ["report-filter-plan"] });
    },
    onError: (err) => {
      const c = configConflict(err);
      if (c) setConflict(c);
      else setSaveError(err instanceof Error ? err.message : String(err));
    },
  });

  const handleSave = () => {
    if (draft) mutation.mutate({ data: draft, version: baseVersion });
  };

  // Keep the edits and replace what is on disk now.
  const handleOverwrite = () => {
    if (draft) mutation.mutate({ data: draft, version: conflict?.currentVersion ?? serverVersion });
  };

  const addKeyword = (type: KeywordList, value: string) => {
    const term = value.trim();
    if (!term) return;
    edit((next) => {
      const rules = rulesOf(next);
      const current = rules[type];
      const list = Array.isArray(current) ? current : [];
      if (!list.includes(term)) list.push(term);
      rules[type] = list;
    });
  };

  const removeKeyword = (type: KeywordList, index: number) => {
    edit((next) => {
      rulesOf(next)[type]?.splice(index, 1);
    });
  };

  const toggleDocType = (docType: string) => {
    edit((next) => {
      const filters = filtersOf(next);
      const list = Array.isArray(filters.document_types) ? filters.document_types : [];
      const idx = list.indexOf(docType);
      if (idx >= 0) list.splice(idx, 1);
      else list.push(docType);
      filters.document_types = list;
    });
  };

  const addVenue = (value: string) => {
    const venue = normalizeVenue(value);
    if (!venue) return;
    edit((next) => {
      const filters = filtersOf(next);
      const list = Array.isArray(filters.venues) ? filters.venues : [];
      if (!list.includes(venue)) list.push(venue);
      filters.venues = list;
    });
  };

  const removeVenue = (index: number) => {
    edit((next) => {
      filtersOf(next).venues?.splice(index, 1);
    });
  };

  const toggleSource = (source: string) => {
    edit((next) => {
      const search = searchOf(next);
      const sources = Array.isArray(search.sources) ? search.sources : [];
      const idx = sources.indexOf(source);
      if (idx >= 0) sources.splice(idx, 1);
      else sources.push(source);
      search.sources = sources;
    });
  };

  const setApiKey = (field: "scopus" | "openalex_key" | "openalex_email", value: string) => {
    edit((next) => {
      keysOf(next)[field] = value;
    });
  };

  const queries = Array.isArray(form.search?.queries) ? form.search.queries : [];
  const docTypes = splitDocTypes(form.search?.filters?.document_types, DOC_TYPES);
  const openalexKeyState = secretState(form.api_keys?.openalex_key, config.api_keys?.openalex_key);
  const readinessNotes = [...(readiness?.problems ?? []), ...(readiness?.warnings ?? [])];

  return (
    <div className="space-y-8">
      <div data-tutorial="settings-header" className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="w-7 h-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
            {projectLabel && <p className="text-xs text-text-muted">Project: {projectLabel}</p>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {dirty && (
            <span className="text-xs font-medium text-accent-amber" role="status">
              Unsaved changes
            </span>
          )}
          <button
            type="button"
            onClick={discard}
            disabled={!dirty || mutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border-glass text-text-secondary hover:border-border-glass-hover hover:text-text-primary disabled:opacity-40"
          >
            <RotateCcw className="w-4 h-4" />
            Discard changes
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!dirty || mutation.isPending}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary text-bg-base font-semibold hover:opacity-90 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {mutation.isPending ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </div>

      {(conflict || changedOnDisk) && (
        <div role="alert" className="glass p-4 border-l-4 border-l-accent-amber space-y-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-accent-amber shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-text-primary">The config changed on disk while you were editing.</p>
              <p className="text-text-secondary">
                {conflict?.message ??
                  "Another tab, the MCP server or an editor saved config.yaml after you started editing."}{" "}
                Reload to see the new version (your unsaved edits are dropped), or overwrite it with your version.
              </p>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={discard}
              className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm border border-border-glass text-text-secondary hover:text-text-primary hover:border-border-glass-hover"
            >
              <RefreshCw className="w-4 h-4" />
              Reload from disk
            </button>
            <button
              type="button"
              onClick={handleOverwrite}
              disabled={mutation.isPending}
              className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm bg-accent-amber/15 text-accent-amber border border-accent-amber/30 hover:bg-accent-amber/25 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              Overwrite with my version
            </button>
          </div>
        </div>
      )}

      {saveError && (
        <div role="alert" className="glass p-3 border-l-4 border-l-accent-red text-sm text-accent-red">
          {saveError}
        </div>
      )}

      {saved && !dirty && (
        <div role="status" className="glass p-3 border-l-4 border-l-accent-green text-accent-green text-sm">
          Configuration saved successfully.
        </div>
      )}

      {readinessNotes.length > 0 && (
        <div className="glass p-4 border-l-4 border-l-accent-amber">
          <p className="text-sm font-semibold text-text-primary mb-1.5">Check before running (saved configuration)</p>
          <ul className="space-y-1">
            {readinessNotes.map((note, i) => (
              <li key={i} className="text-xs text-text-secondary leading-relaxed">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Project */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <FolderOpen className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Project</h2>
        </div>
        <label htmlFor="project-name" className="block text-sm text-text-secondary mb-1">Project Name</label>
        <input
          id="project-name"
          type="text"
          value={form.project?.name ?? ""}
          onChange={(e) => edit((next) => { (next.project ??= {}).name = e.target.value; })}
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
            <label htmlFor="date-start" className="block text-sm text-text-secondary mb-1">Start Date</label>
            <input
              id="date-start"
              type="date"
              value={form.search?.date_range?.start ?? ""}
              onChange={(e) => edit((next) => { (searchOf(next).date_range ??= {}).start = e.target.value; })}
              className="glass-input w-full"
            />
          </div>
          <div>
            <label htmlFor="date-end" className="block text-sm text-text-secondary mb-1">End Date</label>
            <input
              id="date-end"
              type="date"
              value={form.search?.date_range?.end ?? ""}
              onChange={(e) => edit((next) => { (searchOf(next).date_range ??= {}).end = e.target.value; })}
              className="glass-input w-full"
            />
          </div>
          <div>
            <label htmlFor="max-results" className="block text-sm text-text-secondary mb-1">Max Results per Query</label>
            <input
              id="max-results"
              type="number"
              value={form.search?.max_results_per_query ?? 100}
              onChange={(e) =>
                edit((next) => { searchOf(next).max_results_per_query = parseInt(e.target.value) || 0; })
              }
              className="glass-input w-full"
              min={1}
            />
          </div>
        </div>
        <fieldset>
          <legend className="block text-sm text-text-secondary mb-2">Sources</legend>
          <div className="space-y-2">
            {SOURCES.map((source) => {
              const info = SOURCE_INFO[source];
              const checked = (form.search?.sources ?? []).includes(source);
              const missingKey = source === "openalex" && checked && (openalexKeyState === "unset" || openalexKeyState === "removed");
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
                        ({info.note})
                      </span>
                    )}
                    {missingKey && (
                      <span className="ml-1.5 text-xs text-accent-amber">
                        No OpenAlex API key set: large searches can be cut short.
                      </span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
      </GlassCard>

      {/* Search Queries */}
      <GlassCard data-tutorial="search-queries">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Search Queries</h2>
          </div>
          <InfoTip label="How to write queries" variant="header" width="w-80">
            <p className="font-semibold text-text-primary">How to write queries</p>
            <ul className="text-text-secondary space-y-1.5 list-none">
              <li><span className="text-primary font-mono text-xs">OR</span>: between synonyms, <span className="text-text-muted font-mono text-xs">&quot;crop&quot; OR &quot;agriculture&quot;</span></li>
              <li><span className="text-primary font-mono text-xs">AND</span>: between concepts, <span className="text-text-muted font-mono text-xs">&quot;deep learning&quot; AND &quot;remote sensing&quot;</span></li>
              <li><span className="text-primary font-mono text-xs">&quot;...&quot;</span>: exact phrase, <span className="text-text-muted font-mono text-xs">&quot;foundation model&quot;</span></li>
              <li><span className="text-primary font-mono text-xs">( )</span>: grouping, <span className="text-text-muted font-mono text-xs">(&quot;A&quot; OR &quot;B&quot;) AND &quot;C&quot;</span></li>
            </ul>
            <p className="text-text-muted pt-1 border-t border-border-glass">Each query is sent to all selected databases. Use 3-5 focused queries rather than one large query.</p>
          </InfoTip>
        </div>

        {/* Query cards */}
        <div className="space-y-4">
          {queries.map((q, idx) => (
            <div key={idx} className="glass p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-md bg-primary/15 text-primary text-xs font-bold">{idx + 1}</span>
                  <input
                    type="text"
                    aria-label={`Name of query ${idx + 1}`}
                    value={q.name || ""}
                    onChange={(e) => edit((next) => { searchOf(next).queries![idx].name = e.target.value; })}
                    className="glass-input py-1 px-2 text-sm font-medium w-80"
                    placeholder="Query name"
                  />
                </div>
                <button
                  type="button"
                  aria-label={`Remove query ${q.name || idx + 1}`}
                  onClick={() => edit((next) => { searchOf(next).queries?.splice(idx, 1); })}
                  className="text-text-muted hover:text-accent-red p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <textarea
                aria-label={`Terms of query ${idx + 1}`}
                value={q.terms || ""}
                onChange={(e) => edit((next) => { searchOf(next).queries![idx].terms = e.target.value; })}
                rows={3}
                className="glass-input w-full font-mono text-sm leading-relaxed resize-y"
                placeholder={'("term A" OR "term B") AND ("method") AND ("domain")'}
              />
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={() =>
            edit((next) => {
              const search = searchOf(next);
              if (!Array.isArray(search.queries)) search.queries = [];
              search.queries.push({ name: `query_${search.queries.length + 1}`, terms: "" });
            })
          }
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
          <InfoTip label="How screening works" variant="header" width="w-80">
            <p className="font-semibold text-text-primary">How screening works</p>
            <ul className="text-text-secondary space-y-1.5 list-none">
              <li><span className="text-accent-green font-semibold">Include</span>: paper matches ≥ minimum threshold of include keywords AND 0 exclude keywords</li>
              <li><span className="text-accent-red font-semibold">Exclude</span>: paper matches any exclude keyword, OR (if required keywords are set) matches none of them</li>
              <li><span className="text-accent-amber font-semibold">Maybe</span>: not enough include keywords, no exclude match</li>
            </ul>
            <p className="text-text-muted pt-1 border-t border-border-glass">Example: with threshold=4 and 12 include keywords, a paper must mention at least 4 of them in title+abstract to be included.</p>
          </InfoTip>
        </div>

        <KeywordEditor
          id="include-keywords"
          label="Include Keywords"
          items={form.screening?.rules?.include_keywords ?? []}
          chipClass="bg-primary-dim text-primary border border-primary/20"
          addClass="text-primary hover:border-primary/30"
          placeholder='e.g. "foundation model", "remote sensing"'
          input={includeInput}
          setInput={setIncludeInput}
          onAdd={(v) => addKeyword("include_keywords", v)}
          onRemove={(i) => removeKeyword("include_keywords", i)}
        />

        <KeywordEditor
          id="exclude-keywords"
          label="Exclude Keywords"
          items={form.screening?.rules?.exclude_keywords ?? []}
          chipClass="bg-accent-red/15 text-accent-red border border-accent-red/20"
          addClass="text-accent-red hover:border-accent-red/30"
          placeholder='e.g. "medical imaging", "urban", "flood"'
          input={excludeInput}
          setInput={setExcludeInput}
          onAdd={(v) => addKeyword("exclude_keywords", v)}
          onRemove={(i) => removeKeyword("exclude_keywords", i)}
        />

        <KeywordEditor
          id="required-keywords"
          label="Required Keywords"
          items={form.screening?.rules?.required_keywords ?? []}
          chipClass="bg-accent-amber/15 text-accent-amber border border-accent-amber/20"
          addClass="text-accent-amber hover:border-accent-amber/30"
          placeholder='e.g. "wireless", "network"'
          input={requiredInput}
          setInput={setRequiredInput}
          onAdd={(v) => addKeyword("required_keywords", v)}
          onRemove={(i) => removeKeyword("required_keywords", i)}
          info={
            <InfoTip label="About required keywords" variant="inline" width="w-80">
              <p className="text-text-primary font-medium">Optional gate. If any are set, a paper is auto-excluded unless it contains at least one of these terms in its title/abstract (a paper without an abstract is left as &quot;maybe&quot; instead).</p>
              <p className="text-text-muted">Leave empty to disable (default). Each term must appear as a whole word or phrase: case, hyphens and a plural s/es are ignored, so &quot;large language model&quot; matches &quot;Large-Language Models&quot; but &quot;RAG&quot; does not match &quot;storage&quot; and a stem such as &quot;optim&quot; matches nothing. List other word forms separately (optimise, optimize).</p>
            </InfoTip>
          }
        />

        {/* Min Include Hits */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <label htmlFor="min-include-hits" className="block text-sm text-text-secondary">
              Minimum Include Keyword Hits
            </label>
            <InfoTip label="About the include threshold" variant="inline" width="w-72">
              <p className="text-text-primary font-medium">How many include keywords must appear in a paper&apos;s title+abstract for it to pass.</p>
              <p className="text-text-muted">Low (1-2) = permissive, many papers pass</p>
              <p className="text-text-muted">High (4-5) = strict, only highly relevant papers</p>
              <p className="text-accent-amber">Tip: Start with 2, check results, increase if too many pass.</p>
            </InfoTip>
          </div>
          <input
            id="min-include-hits"
            type="number"
            value={form.screening?.rules?.min_include_hits ?? 2}
            onChange={(e) => edit((next) => { rulesOf(next).min_include_hits = parseInt(e.target.value) || 1; })}
            className="glass-input w-32"
            min={1}
            max={10}
          />
        </div>
      </GlassCard>

      {/* More filters (source-side filters) */}
      <GlassCard data-tutorial="more-filters">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">More filters</h2>
          </div>
          <InfoTip label="How filters are applied" variant="header" width="w-96">
            <p className="font-semibold text-text-primary">How filters are applied</p>
            <ul className="text-text-secondary space-y-1.5 list-none">
              <li><span className="text-accent-green font-semibold">Server-side</span>: applied at the request when the source supports the facet (e.g. OpenAlex/Crossref document type, OpenAlex/Scopus open access).</li>
              <li><span className="text-accent-amber font-semibold">Locally</span>: applied after the fetch when the source has no such facet (e.g. abstract on Semantic Scholar, Scopus and arXiv).</li>
              <li><span className="text-accent-red font-semibold">Ignored</span>: when a source can&apos;t evaluate it at all (e.g. open access on Crossref, document types / venues on arXiv).</li>
            </ul>
            <p className="text-text-muted pt-1 border-t border-border-glass">Empty / off everywhere = no filtering (default). Run a search to see the per-source warnings.</p>
          </InfoTip>
        </div>

        {/* Document types */}
        <div className="mb-6">
          <p id="doc-types-label" className="block text-sm text-text-secondary mb-2">Document Types</p>
          <div role="group" aria-labelledby="doc-types-label" className="flex flex-wrap gap-2">
            {DOC_TYPES.map((dt) => {
              const active = docTypes.known.includes(dt);
              return (
                <button
                  type="button"
                  key={dt}
                  aria-pressed={active}
                  onClick={() => toggleDocType(dt)}
                  className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                    active
                      ? "bg-primary-dim text-primary border-primary/30"
                      : "text-text-muted border-border-glass hover:border-border-glass-hover hover:text-text-secondary"
                  }`}
                >
                  {dt}
                </button>
              );
            })}
            {docTypes.unknown.map((dt) => (
              <span
                key={dt}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-accent-amber/15 text-accent-amber border border-accent-amber/30"
                title="Not a document type the search filters know; remove it or pick one of the types on the left."
              >
                {dt} (not recognised)
                <button
                  type="button"
                  aria-label={`Remove document type ${dt}`}
                  onClick={() => toggleDocType(dt)}
                  className="hover:text-text-primary"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <p className="text-xs text-text-muted mt-2">
            {docTypes.known.length + docTypes.unknown.length === 0 ? "None selected = all types. " : ""}
            Not every type exists in every source (e.g. arXiv is preprint-only).
          </p>
        </div>

        {/* Toggles */}
        <div className="mb-6 space-y-2">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.search?.filters?.require_abstract ?? false}
              onChange={(e) => edit((next) => { filtersOf(next).require_abstract = e.target.checked; })}
              className="w-4 h-4 accent-primary rounded shrink-0"
            />
            <span className="text-sm">
              <span className="text-text-primary font-medium">Require abstract</span>
              <span className="ml-1.5 text-xs text-text-muted">(drop records with no abstract, needed for keyword screening)</span>
            </span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.search?.filters?.open_access ?? false}
              onChange={(e) => edit((next) => { filtersOf(next).open_access = e.target.checked; })}
              className="w-4 h-4 accent-primary rounded shrink-0"
            />
            <span className="text-sm">
              <span className="text-text-primary font-medium">Open access only</span>
              <span className="ml-1.5 text-xs text-text-muted">(keep only open-access records)</span>
            </span>
          </label>
        </div>

        {/* Venues / ISSN */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label htmlFor="venues-input" className="block text-sm text-text-secondary">Venues / ISSN</label>
            <InfoTip label="About venue filters" variant="inline" width="w-80">
              <p className="text-text-primary font-medium">Restrict to specific journals.</p>
              <p className="text-text-muted">Add an ISSN (e.g. &quot;1234-567X&quot;; &quot;1234567X&quot; is fixed for you) or a journal name. ISSNs filter server-side on OpenAlex/Crossref/Scopus; names match the venue field (often locally).</p>
            </InfoTip>
          </div>
          <div className="flex flex-wrap gap-2 mb-2">
            {(form.search?.filters?.venues ?? []).map((v, i) => {
              const issn = isIssn(v);
              return (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm bg-primary-dim text-primary border border-primary/20"
                  title={issn ? "Filtered as an ISSN" : "Matched against the journal name (not an ISSN of the form 1234-567X)"}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wide ${issn ? "text-accent-green" : "text-text-muted"}`}>
                    {issn ? "ISSN" : "name"}
                  </span>
                  {v}
                  <button
                    type="button"
                    aria-label={`Remove venue ${v}`}
                    onClick={() => removeVenue(i)}
                    className="hover:text-text-primary"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              );
            })}
          </div>
          <div className="flex gap-2 max-w-md">
            <input
              id="venues-input"
              type="text"
              value={venuesInput}
              onChange={(e) => setVenuesInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addVenue(venuesInput);
                  setVenuesInput("");
                }
              }}
              className="glass-input flex-1"
              placeholder='ISSN "1234-567X" or journal name'
            />
            <button
              type="button"
              aria-label="Add venue"
              onClick={() => {
                addVenue(venuesInput);
                setVenuesInput("");
              }}
              className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border-glass text-primary hover:border-primary/30"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
      </GlassCard>

      {/* API Keys */}
      <GlassCard data-tutorial="api-keys">
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">API Keys</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <SecretKeyInput
            id="openalex-key"
            label="OpenAlex API Key"
            value={form.api_keys?.openalex_key}
            stored={config.api_keys?.openalex_key}
            onChange={(v) => setApiKey("openalex_key", v)}
            placeholder="Enter OpenAlex API key"
            hint="OpenAlex limits how many results a query can return without a free API key."
            info={
              <InfoTip label="How to get an OpenAlex API key" variant="inline" width="w-80">
                <p className="text-text-primary font-medium">OpenAlex API key (free)</p>
                <p className="text-text-muted">Without a key OpenAlex gives a much smaller daily request budget and limits how far a query can page, so a large search can be cut short (the run then reports the query as partial).</p>
                <p className="text-text-muted">Create a free key at <span className="text-primary">openalex.org/settings/api</span> and paste it here.</p>
              </InfoTip>
            }
          />
          <SecretKeyInput
            id="scopus-key"
            label="Scopus API Key (optional, free to get)"
            value={form.api_keys?.scopus}
            stored={config.api_keys?.scopus}
            onChange={(v) => setApiKey("scopus", v)}
            placeholder="Enter Scopus API key"
            info={
              <InfoTip label="How to get a Scopus API key" variant="inline" align="right" width="w-80">
                <p className="text-text-primary font-medium">Elsevier Scopus API Key</p>
                <p className="text-text-muted">1. Go to <span className="text-primary">dev.elsevier.com</span> and create an account (free)</p>
                <p className="text-text-muted">2. Click &quot;Create API Key&quot;</p>
                <p className="text-text-muted">3. Label: <span className="text-primary">PRISMA Review Tool</span></p>
                <p className="text-text-muted">4. Website: <span className="text-primary">http://localhost</span></p>
                <p className="text-text-muted">5. Copy the generated key and paste it here</p>
                <p className="text-accent-amber">The API key is free for anyone. For full results (abstracts, complete records), use from a campus network or university VPN. Basic metadata (titles, authors, DOIs) works from anywhere.</p>
                <p className="text-text-muted">This key also enables Elsevier PDF downloads for papers your institution subscribes to.</p>
              </InfoTip>
            }
          />
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label htmlFor="openalex-email" className="block text-sm text-text-secondary">OpenAlex Email (optional)</label>
              <InfoTip label="About the OpenAlex email" variant="inline" width="w-80">
                <p className="text-text-primary font-medium">Contact email for OpenAlex</p>
                <p className="text-text-muted">Optional. Sent to OpenAlex as your contact address. It does not replace the API key, which is what raises the request limits.</p>
              </InfoTip>
            </div>
            <input
              id="openalex-email"
              type="text"
              value={form.api_keys?.openalex_email ?? ""}
              onChange={(e) => setApiKey("openalex_email", e.target.value)}
              className="glass-input w-full"
              placeholder="your@email.com"
            />
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

/**
 * The (i) help bubble. Opens on hover and on keyboard focus (WEB#17).
 * "header" sits at the right of a card title, "inline" next to a field label.
 */
function InfoTip({
  label,
  variant,
  width,
  align,
  children,
}: {
  label: string;
  variant: "header" | "inline";
  width: string;
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  const header = variant === "header";
  const side = (align ?? (header ? "right" : "left")) === "right" ? "right-0" : "left-0";
  const place = header ? `${side} top-9 p-4 text-sm space-y-2` : `${side} bottom-7 p-3 text-xs space-y-1.5`;
  return (
    <div className="relative group">
      <button
        type="button"
        aria-label={label}
        className={`flex items-center justify-center rounded-full bg-primary/10 text-primary hover:bg-primary/20 font-bold ${
          header ? "w-7 h-7 text-sm" : "w-5 h-5 text-[10px]"
        }`}
      >
        i
      </button>
      <div
        role="tooltip"
        className={`absolute ${place} ${width} glass-elevated rounded-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible group-focus-within:opacity-100 group-focus-within:visible z-50 shadow-xl`}
      >
        {children}
      </div>
    </div>
  );
}

function KeywordEditor({
  id,
  label,
  items,
  chipClass,
  addClass,
  placeholder,
  input,
  setInput,
  onAdd,
  onRemove,
  info,
}: {
  id: string;
  label: string;
  items: string[];
  chipClass: string;
  addClass: string;
  placeholder: string;
  input: string;
  setInput: (v: string) => void;
  onAdd: (v: string) => void;
  onRemove: (index: number) => void;
  info?: React.ReactNode;
}) {
  const add = () => {
    onAdd(input);
    setInput("");
  };
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-2">
        <label htmlFor={id} className="block text-sm text-text-secondary">{label}</label>
        {info}
      </div>
      <div className="flex flex-wrap gap-2 mb-2">
        {items.map((kw, i) => (
          <span key={i} className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm ${chipClass}`}>
            {kw}
            <button
              type="button"
              aria-label={`Remove ${label.toLowerCase().replace(/s$/, "")} ${kw}`}
              onClick={() => onRemove(i)}
              className="hover:text-text-primary"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2 max-w-md">
        <input
          id={id}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="glass-input flex-1"
          placeholder={placeholder}
        />
        <button
          type="button"
          aria-label={`Add ${label.toLowerCase().replace(/s$/, "")}`}
          onClick={add}
          className={`flex items-center gap-1 px-3 py-2 rounded-lg border border-border-glass ${addClass}`}
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

/**
 * An API key field. The API never sends a stored key back, only "********";
 * that value is kept out of the box (so typing cannot append to it) and is
 * sent back unchanged on save, which the API reads as "keep the stored key".
 */
function SecretKeyInput({
  id,
  label,
  value,
  stored,
  onChange,
  placeholder,
  hint,
  info,
}: {
  id: string;
  label: string;
  value: string | undefined;
  stored: string | undefined;
  onChange: (value: string) => void;
  placeholder: string;
  hint?: string;
  info?: React.ReactNode;
}) {
  const state = secretState(value, stored);
  const badge = {
    stored: { text: "Saved", cls: "text-accent-green bg-accent-green/10 border-accent-green/20" },
    new: { text: "New, not saved yet", cls: "text-primary bg-primary/10 border-primary/20" },
    removed: { text: "Removed on save", cls: "text-accent-red bg-accent-red/10 border-accent-red/20" },
    unset: { text: "Not set", cls: "text-text-muted bg-bg-glass border-border-glass" },
  }[state];
  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <label htmlFor={id} className="block text-sm text-text-secondary">{label}</label>
        {info}
        <span className={`ml-auto text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${badge.cls}`}>
          {badge.text}
        </span>
      </div>
      <div className="flex gap-2">
        <input
          id={id}
          type="password"
          autoComplete="off"
          value={secretDisplayValue(value)}
          onChange={(e) => onChange(secretInputValue(e.target.value, stored))}
          className="glass-input w-full"
          placeholder={
            state === "stored"
              ? "Saved key hidden. Type to replace it."
              : state === "removed"
                ? "The saved key will be removed when you save"
                : placeholder
          }
        />
        {state === "stored" && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="px-3 py-2 rounded-lg text-xs border border-border-glass text-text-secondary hover:text-accent-red hover:border-accent-red/30"
          >
            Remove
          </button>
        )}
        {state === "removed" && (
          <button
            type="button"
            onClick={() => onChange(SECRET_MASK)}
            className="px-3 py-2 rounded-lg text-xs border border-border-glass text-text-secondary hover:text-text-primary"
          >
            Undo
          </button>
        )}
      </div>
      {hint && <p className="text-xs text-text-muted mt-1">{hint}</p>}
    </div>
  );
}
