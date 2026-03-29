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

// Paper details & search
export const fetchPaper = (id: string) => request<PaperDetail>(`/api/papers/${id}`);
export const searchPapers = (q: string) => request<SearchResponse>(`/api/papers/search?q=${encodeURIComponent(q)}`);

// Pipeline
export const fetchPipelineStatus = () => request<any>("/api/pipeline/status");
export const runPipelineStep = (step: string) => request<any>(`/api/pipeline/${step}`, { method: "POST" });

// Reports
export const generateReport = () => request<any>("/api/reports/generate", { method: "POST" });
export const downloadPapers = () => request<any>("/api/papers/download", { method: "POST" });

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

export interface SearchResponse {
  query: string;
  matches: number;
  papers: { id: string; title: string; year: number; source: string; decision: string | null }[];
}
