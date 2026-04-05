const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...opts?.headers },
    ...opts,
  });
  return res.json();
}

// Stats
export const fetchStats = () => request<StatsResponse>("/api/stats");

// Papers - screening
export const fetchPapersToScreen = (batchSize = 20, filter = "maybe") =>
  request<PaperListResponse>(`/api/papers/screen?batch_size=${batchSize}&filter_type=${filter}`);

export const screenPaper = (id: string, decision: string, reason: string) =>
  request<any>(`/api/papers/${id}/screen`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });

export const batchScreen = (decisions: { paper_id: string; decision: string; reason: string }[]) =>
  request<any>("/api/papers/screen/batch", {
    method: "POST",
    body: JSON.stringify(decisions),
  });

// Papers - eligibility
export const fetchEligibilityPapers = (batchSize = 20) =>
  request<EligibilityListResponse>(`/api/papers/eligibility?batch_size=${batchSize}`);

export const eligibilityScreen = (id: string, decision: string, reason: string) =>
  request<any>(`/api/papers/${id}/eligibility`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });

// Browse all papers (paginated)
export const fetchAllPapers = (page = 1, perPage = 20, decision = "all", source = "all") =>
  request<PaginatedPapersResponse>(`/api/papers?page=${page}&per_page=${perPage}&decision=${decision}&source=${source}`);

// Re-screen with different threshold
export const rescreenPapers = (minIncludeHits: number) =>
  request<{ status: string; included: number; excluded: number; maybe: number }>(
    `/api/papers/rescreen?min_include_hits=${minIncludeHits}`,
    { method: "POST" },
  );

// Paper details & search
export const fetchPaper = (id: string) => request<PaperDetail>(`/api/papers/${id}`);
export const searchPapers = (q: string) => request<SearchResponse>(`/api/papers/search?q=${encodeURIComponent(q)}`);

// Pipeline — synchronous (legacy)
export const fetchPipelineStatus = () => request<any>("/api/pipeline/status");
export const runPipelineStep = (step: string) => request<any>(`/api/pipeline/${step}`, { method: "POST" });

// Pipeline — background session
export const startPipeline = () =>
  request<{ status: string; session_id: string }>("/api/pipeline/start", { method: "POST" });
export const startPipelineStep = (step: string) =>
  request<{ status: string; session_id: string; step: string }>(`/api/pipeline/start/${step}`, { method: "POST" });
export const fetchPipelineProgress = () => request<PipelineProgress>("/api/pipeline/progress");
export const stopPipeline = () =>
  request<{ status: string }>("/api/pipeline/stop", { method: "POST" });

// Reports
export const generateReport = () => request<any>("/api/reports/generate", { method: "POST" });
export const downloadPapers = () => request<any>("/api/papers/download", { method: "POST" });
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
  if (!res.ok) throw new Error("Export failed");
  return res.blob();
};
export const importProject = async (file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/api/projects/import`, { method: "POST", body: form });
  return res.json() as Promise<{ status: string; name: string }>;
};

// UI state (per-project filter persistence)
export const fetchUiState = () => request<Record<string, any>>("/api/projects/active/ui-state");
export const saveUiState = (state: Record<string, any>) =>
  request<{ status: string }>("/api/projects/active/ui-state", {
    method: "PUT",
    body: JSON.stringify(state),
  });

// Config
export const fetchConfig = () => request<any>("/api/config");
export const updateConfig = (data: any) =>
  request<any>("/api/config", { method: "PUT", body: JSON.stringify(data) });

// Types
export interface StatsResponse {
  project: string;
  search: Record<string, number>;
  dedup: Record<string, number>;
  screen: Record<string, number>;
  eligibility: Record<string, number>;
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
  result: Record<string, any> | null;
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
}

export interface ActiveProjectResponse {
  active: string | null;
  display_name?: string;
}
