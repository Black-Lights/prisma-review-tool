import type { PrismaFlow } from "./flow";

/** Base URL of the FastAPI backend. The only place the env var is read. */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API = API_BASE;

/**
 * A non-2xx API response. `detail` is FastAPI's `detail` field: usually a
 * string, or an object such as {error: "config_changed", message, ...}.
 */
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(describeError(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function describeError(status: number, detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return `Request failed with HTTP ${status}`;
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...opts?.headers },
  });
  return parseResponse<T>(res);
}

/** The JSON body of a 2xx response; anything else throws an ApiError. */
async function parseResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : body;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

// Stats
export const fetchStats = () => request<StatsResponse>("/api/stats");

// Papers - screening
export const fetchPapersToScreen = (batchSize = 20, filter = "maybe") =>
  request<PaperListResponse>(`/api/papers/screen?batch_size=${batchSize}&filter_type=${filter}`);

export const screenPaper = (id: string, decision: string, reason: string) =>
  request<Record<string, unknown>>(`/api/papers/${encodeURIComponent(id)}/screen`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });

export const batchScreen = (decisions: { paper_id: string; decision: string; reason: string }[]) =>
  request<Record<string, unknown>>("/api/papers/screen/batch", {
    method: "POST",
    body: JSON.stringify(decisions),
  });

// Papers - eligibility
export const fetchEligibilityPapers = (batchSize = 20) =>
  request<EligibilityListResponse>(`/api/papers/eligibility?batch_size=${batchSize}`);

export const eligibilityScreen = (id: string, decision: string, reason: string) =>
  request<Record<string, unknown>>(`/api/papers/${encodeURIComponent(id)}/eligibility`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });

// Browse all papers (paginated)

// Columns the backend sorts by (api/routes/papers.py, _SORT_KEYS). A value
// saved in the URL or ui_state.json outside this list made every request 422.
export const SORT_KEYS = ["title", "authors", "year", "source", "decision"] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export function normalizeSort(value: unknown): SortKey | "" {
  return (SORT_KEYS as readonly unknown[]).includes(value) ? (value as SortKey) : "";
}

// Rows per page offered by All Papers (the backend accepts 1..1000).
export const PER_PAGE_OPTIONS = [25, 50, 100, 250, 500, 1000] as const;

/** The nearest offered page size at or above `value` (25 when unusable). */
export function normalizePerPage(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 1) return PER_PAGE_OPTIONS[0];
  return PER_PAGE_OPTIONS.find((size) => size >= n) ?? PER_PAGE_OPTIONS[PER_PAGE_OPTIONS.length - 1];
}

export const fetchAllPapers = (
  page = 1,
  perPage = 20,
  decision = "all",
  source = "all",
  sort = "",
  order: "asc" | "desc" = "asc",
) => {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
    decision,
    source,
  });
  const sortKey = normalizeSort(sort);
  if (sortKey) {
    params.set("sort", sortKey);
    params.set("order", order === "desc" ? "desc" : "asc");
  }
  return request<PaginatedPapersResponse>(`/api/papers?${params}`);
};

// Re-screen with different threshold
export const rescreenPapers = (minIncludeHits: number) =>
  request<{ status: string; min_include_hits: number; included: number; excluded: number; maybe: number;
            kept_manual?: number; kept_ai?: number; eligibility_set_aside?: number }>(
    `/api/papers/rescreen?min_include_hits=${minIncludeHits}`,
    { method: "POST" },
  );

// Paper details & search
export const fetchPaper = (id: string) => request<PaperDetail>(`/api/papers/${encodeURIComponent(id)}`);
export const searchPapers = (q: string) => request<SearchResponse>(`/api/papers/search?q=${encodeURIComponent(q)}`);

// Pipeline — synchronous (legacy)
export const fetchPipelineStatus = () => request<Record<string, unknown>>("/api/pipeline/status");
export const runPipelineStep = (step: string) =>
  request<Record<string, unknown>>(`/api/pipeline/${encodeURIComponent(step)}`, { method: "POST" });

// Pipeline — background session
export const startPipeline = () =>
  request<{ status: string; session_id: string }>("/api/pipeline/start", { method: "POST" });
export const startPipelineStep = (step: string) =>
  request<{ status: string; session_id: string; step: string }>(`/api/pipeline/start/${step}`, { method: "POST" });
export const fetchPipelineProgress = () => request<PipelineProgress>("/api/pipeline/progress");
export const stopPipeline = () =>
  request<{ status: string }>("/api/pipeline/stop", { method: "POST" });

// Reports
export const fetchReportByQuery = () => request<ReportByQueryResponse>("/api/reports/by-query");
export const fetchFilterPlan = () => request<FilterPlanResponse>("/api/reports/filter-plan");
export const generateReport = () => request<Record<string, unknown>>("/api/reports/generate", { method: "POST" });
export const downloadPapers = () => request<Record<string, unknown>>("/api/papers/download", { method: "POST" });
export const fetchDownloadLog = () => request<DownloadLogResponse>("/api/papers/downloads");

export interface DownloadEntry {
  id: string;
  title: string;
  file: string | null;
  status: "downloaded" | "exists" | "no_oa" | "failed";
  doi: string | null;
}

export interface DownloadLogResponse {
  total: number;
  downloaded: number;
  no_oa: number;
  failed: number;
  papers: DownloadEntry[];
}

// Projects
export const fetchProjects = () => request<ProjectListResponse>("/api/projects");
export const fetchActiveProject = () => request<ActiveProjectResponse>("/api/projects/active");
export const createProject = (name: string) =>
  request<{ status: string; name: string; display_name: string }>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
export const switchProject = (name: string) =>
  request<{ status: string; active: string }>(`/api/projects/${encodeURIComponent(name)}/switch`, {
    method: "POST",
  });
export const deleteProject = (name: string) =>
  request<{ status: string }>(`/api/projects/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
export const duplicateProject = (name: string, newName: string) =>
  request<{ status: string; name: string }>(`/api/projects/${encodeURIComponent(name)}/duplicate`, {
    method: "POST",
    body: JSON.stringify({ new_name: newName }),
  });
export const exportProject = async (name: string) => {
  const res = await fetch(`${API}/api/projects/export/${encodeURIComponent(name)}`);
  if (!res.ok) return parseResponse<never>(res);
  return res.blob();
};
export const importProject = async (file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/api/projects/import`, { method: "POST", body: form });
  return parseResponse<{ status: string; name: string }>(res);
};

// UI state (per-project filter persistence)
export const fetchUiState = () => request<Record<string, any>>("/api/projects/active/ui-state");
export const saveUiState = (state: Record<string, any>) =>
  request<{ status: string }>("/api/projects/active/ui-state", {
    method: "PUT",
    body: JSON.stringify(state),
  });

// Config
// GET returns the raw config plus "_version" ("<mtime_ns>-<size>") with API
// key values masked as "********". PUT takes the whole config: send back the
// _version it was loaded with (409 detail.error "config_changed" when the file
// changed since) and "********" for any key left unchanged.
export const fetchConfig = () => request<ConfigData>("/api/config");
export const updateConfig = (data: ConfigData) =>
  request<{ status: string; _version: string | null }>("/api/config", { method: "PUT", body: JSON.stringify(data) });
export const fetchConfigReadiness = () => request<ConfigReadiness>("/api/config/readiness");

// Types
export interface StatsResponse {
  project: string;
  search: Record<string, number>;
  dedup: Record<string, number>;
  screen: Record<string, number>;
  eligibility: Record<string, number>;
  /** PRISMA 2020 flow counts; the diagram and the report render only these. */
  flow?: PrismaFlow;
  /** Set (with no other field) when the project has no pipeline state yet. */
  error?: string;
}

export interface QueryDef {
  name?: string;
  terms?: string;
  [key: string]: unknown;
}

export interface SearchFilters {
  document_types?: string[];
  require_abstract?: boolean;
  open_access?: boolean;
  venues?: string[];
  [key: string]: unknown;
}

/** The config.yaml mapping as the API returns it. Unknown keys are kept on save. */
export interface ConfigData {
  _version?: string | null;
  project?: { name?: string; [key: string]: unknown };
  search?: {
    sources?: string[];
    date_range?: { start?: string; end?: string; [key: string]: unknown };
    max_results_per_query?: number;
    queries?: QueryDef[];
    filters?: SearchFilters;
    [key: string]: unknown;
  };
  screening?: {
    rules?: {
      include_keywords?: string[];
      exclude_keywords?: string[];
      required_keywords?: string[];
      min_include_hits?: number;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  api_keys?: { scopus?: string; openalex_key?: string; openalex_email?: string; [key: string]: unknown };
  [key: string]: unknown;
}

export interface ConfigReadiness {
  ready: boolean;
  problems: string[];
  search_problems: string[];
  screen_problems: string[];
  warnings: string[];
}

export interface QueryReportRow {
  name: string;
  terms: string;
  found_raw: number;
  after_dedup: number;
  included: number;
  maybe: number;
  excluded: number;
}

export interface ReportByQueryResponse {
  queries: QueryReportRow[];
  total_after_dedup: number;
  total_included: number;
  untagged: { raw: number; screened: number };
  error?: string;
}

export type FilterMode = "request" | "post" | "unsupported";

export interface FilterPlanResponse {
  sources: string[];
  filters: { filter: string; by_source: Record<string, FilterMode> }[];
  empty: boolean;
  error?: string;
}

export interface PaperSummary {
  id: string;
  title: string;
  authors: string;
  year: number;
  abstract: string;
  venue: string;
  source: string;
  doi: string;
  current_decision: string | null;
  current_reason: string | null;
  screen_decision?: string | null;
  screen_reason?: string | null;
}

export interface PaperDetail {
  id: string;
  title: string;
  authors: string[];
  year: number;
  abstract: string;
  venue: string | null;
  doi: string | null;
  url: string | null;
  source: string;
  keywords: string[];
  screen_decision: string | null;
  screen_reason: string | null;
  screen_method: string | null;
  eligibility_decision: string | null;
  eligibility_reason: string | null;
  eligibility_method: string | null;
}

export interface PaperListResponse {
  total_matching: number;
  returned: number;
  papers: PaperSummary[];
}

export interface EligibilityListResponse {
  total_first_pass_included: number;
  already_screened: number;
  remaining: number;
  returned: number;
  papers: PaperSummary[];
}

export interface PaginatedPapersResponse {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  papers: { id: string; title: string; authors: string; year: number; source: string; venue: string; doi: string; decision: string | null; eligibility: string | null }[];
}

export interface SearchResponse {
  query: string;
  matches: number;
  papers: { id: string; title: string; year: number; source: string; decision: string | null }[];
}

export type PipelineStatusType = "idle" | "running" | "completed" | "failed" | "cancelled";

export interface PipelineProgress {
  session_id: string | null;
  status: PipelineStatusType;
  current_step: string | null;
  progress_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  completed_steps: string[];
  warnings: string[];
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface Project {
  name: string;
  display_name: string;
  is_active: boolean;
  paper_counts: {
    search: number;
    dedup: number;
    screened: number;
    eligible: number;
  };
}

export interface ProjectListResponse {
  projects: Project[];
  /** Why the active-project marker is unusable (stale or invalid name). */
  active_error?: string;
}

export interface ActiveProjectResponse {
  active: string | null;
  display_name?: string;
  error?: string;
}
