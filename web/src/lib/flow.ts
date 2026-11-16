/**
 * PRISMA 2020 flow counts as served by GET /api/stats ("flow"). The backend
 * computes them once (prisma_review/stats.py, compute_flow) for the API, the
 * PNG/Markdown diagram and the MCP report, and guarantees the arithmetic
 * closes. The web UI renders these numbers as they are and does no
 * arithmetic of its own (PIPE#12, WEB#4).
 */

export interface PrismaFlow {
  identified: { total: number; by_source: Record<string, number> };
  removed_before_screening: {
    duplicates: number;
    automation_ineligible: number;
    automation_by_reason: { keyword_rules: number; required_keywords: number };
  };
  /** False before keyword screening has run: every record is then not yet screened. */
  screening_started?: boolean;
  /** Records with a screening decision (AI, manual, or included by the keyword rules). */
  screened: number;
  /** Of the screened records, those the keyword rules included without a reviewer. */
  included_by_automation?: number;
  screening_excluded: number;
  /** Optional split of screening_excluded (PRISMA asks human vs automation). */
  screening_excluded_by_method?: Record<string, number>;
  /** Records not yet screened (no decision recorded): neither screened nor excluded. */
  awaiting_screening: number;
  sought_for_retrieval: number;
  assessed_for_eligibility: number;
  eligibility_excluded: number;
  awaiting_eligibility: number;
  included: number;
  notes: string[];
}

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** stats.flow when it has the contract shape, else null (no state yet, or an older API). */
export function getFlow(stats: unknown): PrismaFlow | null {
  if (!stats || typeof stats !== "object") return null;
  const flow = (stats as { flow?: unknown }).flow as Partial<PrismaFlow> | undefined;
  if (!flow || typeof flow !== "object") return null;
  const removed = flow.removed_before_screening;
  const ok =
    isCount(flow.identified?.total) &&
    isCount(removed?.duplicates) &&
    isCount(removed?.automation_ineligible) &&
    [
      flow.screened,
      flow.screening_excluded,
      flow.awaiting_screening,
      flow.sought_for_retrieval,
      flow.assessed_for_eligibility,
      flow.eligibility_excluded,
      flow.awaiting_eligibility,
      flow.included,
    ].every(isCount);
  if (!ok) return null;
  const full = flow as PrismaFlow;
  return { ...full, notes: Array.isArray(full.notes) ? full.notes : [] };
}

export interface FunnelRow {
  key: string;
  label: string;
  /** Extra breakdown shown after the label, e.g. "manual 3, ai 18". */
  detail?: string;
  count: number;
  /** 0 = a PRISMA box, 1 = a breakdown line under the box above. */
  level: 0 | 1;
  accent?: "green" | "amber" | "red";
}

const METHOD_LABEL: Record<string, string> = { manual: "human", ai: "AI-assisted" };

/** "human: 3, AI-assisted: 18" from {manual: 3, ai: 18}; undefined when absent. */
export function byMethod(counts: Record<string, number> | undefined): string | undefined {
  if (!counts || typeof counts !== "object") return undefined;
  const parts = Object.entries(counts)
    .filter(([, n]) => isCount(n))
    .map(([method, n]) => `${METHOD_LABEL[method] ?? method}: ${n}`);
  return parts.length ? parts.join(", ") : undefined;
}

/** The report funnel, one row per PRISMA count, in diagram order. */
export function flowFunnelRows(flow: PrismaFlow): FunnelRow[] {
  const removed = flow.removed_before_screening;
  const reasons = removed.automation_by_reason ?? { keyword_rules: 0, required_keywords: 0 };
  return [
    { key: "identified", label: "Records identified (databases)", count: flow.identified.total, level: 0 },
    ...Object.entries(flow.identified.by_source ?? {}).map(([source, count]): FunnelRow => ({
      key: `source:${source}`,
      label: source,
      count,
      level: 1,
    })),
    { key: "duplicates", label: "Duplicate records removed", count: removed.duplicates, level: 0, accent: "red" },
    {
      key: "automation",
      label: "Marked ineligible by automation tools",
      count: removed.automation_ineligible,
      level: 0,
      accent: "red",
    },
    {
      key: "automation:keyword_rules",
      label: "Exclude-keyword rules",
      count: reasons.keyword_rules,
      level: 1,
    },
    { key: "automation:required_keywords", label: "Required-keyword gate", count: reasons.required_keywords, level: 1 },
    {
      key: "awaiting_screening",
      label: "Not yet screened (no decision recorded)",
      count: flow.awaiting_screening,
      level: 0,
      accent: "amber",
    },
    {
      key: "screened",
      label: "Records screened",
      detail: flow.included_by_automation
        ? `${flow.included_by_automation} included by keyword rules, no reviewer`
        : undefined,
      count: flow.screened,
      level: 0,
    },
    {
      key: "screening_excluded",
      label: "Excluded by reviewers at screening",
      detail: byMethod(flow.screening_excluded_by_method),
      count: flow.screening_excluded,
      level: 1,
      accent: "red",
    },
    { key: "sought_for_retrieval", label: "Reports sought for retrieval", count: flow.sought_for_retrieval, level: 0 },
    {
      key: "assessed_for_eligibility",
      label: "Reports assessed for eligibility",
      count: flow.assessed_for_eligibility,
      level: 0,
    },
    {
      key: "eligibility_excluded",
      label: "Excluded at eligibility",
      count: flow.eligibility_excluded,
      level: 1,
      accent: "red",
    },
    {
      key: "awaiting_eligibility",
      label: "Awaiting eligibility assessment",
      count: flow.awaiting_eligibility,
      level: 1,
      accent: "amber",
    },
    { key: "included", label: "Studies included in review", count: flow.included, level: 0, accent: "green" },
  ];
}
