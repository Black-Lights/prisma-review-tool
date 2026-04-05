"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";

export interface TutorialStep {
  id: string;
  target: string | null; // CSS selector, null = centered card (no highlight)
  title: string;
  description: string;
  page: string; // route where element lives
}

export const TUTORIAL_STEPS: TutorialStep[] = [
  // ── 1. WELCOME ──
  {
    id: "welcome",
    target: null,
    title: "Welcome to PRISMA Review Tool!",
    description: "Let's take a quick tour of the app following the PRISMA 2020 workflow: Settings → Dashboard → Screening → Eligibility → Papers → Downloads.",
    page: "/",
  },
  // ── 2. SETTINGS (configure first) ──
  {
    id: "settings-intro",
    target: '[data-tutorial="settings-header"]',
    title: "Step 1: Settings",
    description: "Start here. Configure your search queries, screening keywords, date range, and database sources before running the pipeline.",
    page: "/settings",
  },
  {
    id: "search-queries",
    target: '[data-tutorial="search-queries"]',
    title: "Search Queries",
    description: "Define Boolean search queries using AND/OR operators. Each query is sent to all selected databases (OpenAlex, Scopus, arXiv, Semantic Scholar).",
    page: "/settings",
  },
  {
    id: "screening-rules",
    target: '[data-tutorial="screening-rules"]',
    title: "Screening Rules",
    description: "Set include and exclude keywords. Papers matching enough include keywords (and no exclude keywords) pass the first screening. You can adjust the threshold later from the Screening page.",
    page: "/settings",
  },
  {
    id: "api-keys",
    target: '[data-tutorial="api-keys"]',
    title: "API Keys",
    description: "Optional but recommended. Add your Scopus API key for broader search coverage and Elsevier PDF downloads. Hover the (i) buttons for step-by-step setup instructions.",
    page: "/settings",
  },
  // ── 3. PROJECTS ──
  {
    id: "projects-intro",
    target: '[data-tutorial="projects-header"]',
    title: "Step 2: Projects",
    description: "Manage multiple literature reviews. Create, switch, duplicate, or export projects — each with its own config, search results, and screening decisions.",
    page: "/projects",
  },
  // ── 4. DASHBOARD (run pipeline) ──
  {
    id: "sidebar",
    target: '[data-tutorial="sidebar"]',
    title: "Navigation",
    description: "Use the sidebar to navigate between pages. The active project is shown at the top. Click 'Take Tour' at the bottom to restart this tutorial anytime.",
    page: "/",
  },
  {
    id: "stat-cards",
    target: '[data-tutorial="stat-cards"]',
    title: "Step 3: Dashboard",
    description: "Pipeline statistics at a glance — from initial search results through deduplication, screening, to final eligible papers.",
    page: "/",
  },
  {
    id: "prisma-diagram",
    target: '[data-tutorial="prisma-diagram"]',
    title: "PRISMA 2020 Flow Diagram",
    description: "Your PRISMA 2020 flow diagram updates automatically as you progress. Click Download PNG to save it for your thesis or paper.",
    page: "/",
  },
  {
    id: "pipeline-stepper",
    target: '[data-tutorial="pipeline-stepper"]',
    title: "Pipeline",
    description: "Run the full pipeline: Search → Deduplicate → Keyword Screening. Green checkmarks show completed steps. The pipeline runs in the background.",
    page: "/",
  },
  {
    id: "run-all",
    target: '[data-tutorial="run-all"]',
    title: "Run All",
    description: "Click to start the pipeline. It searches databases, removes duplicates, and applies keyword screening — all in the background. You can navigate to other pages while it runs.",
    page: "/",
  },
  // ── 5. SCREENING (first pass) ──
  {
    id: "screening-intro",
    target: '[data-tutorial="screening-header"]',
    title: "Step 4: Screening (1st Pass)",
    description: "After the pipeline runs, papers are classified as Included, Excluded, or Maybe. Review 'Maybe' papers here and make manual decisions.",
    page: "/screening",
  },
  {
    id: "rescreen",
    target: '[data-tutorial="screening-header"]',
    title: "Re-screen",
    description: "Click 'Re-screen' to adjust the minimum keyword hits threshold without re-running the whole pipeline. The new value syncs with Settings automatically.",
    page: "/screening",
  },
  {
    id: "filter-pills",
    target: '[data-tutorial="filter-pills"]',
    title: "Filter Papers",
    description: "Filter by status — Maybe (needs review), Included, or Excluded. Start with 'Maybe' to review papers that need your attention.",
    page: "/screening",
  },
  {
    id: "paper-card",
    target: '[data-tutorial="paper-card"]',
    title: "Paper Card",
    description: "Each card shows title, authors, year, source, and abstract. Click the title for full details. Use 'Show More' to expand the abstract.",
    page: "/screening",
  },
  {
    id: "decision-buttons",
    target: '[data-tutorial="decision-controls"]',
    title: "Make Decisions",
    description: "Click Include or Exclude. Add a brief reason — this is documented for PRISMA compliance and appears in the PRISMA flow diagram.",
    page: "/screening",
  },
  // ── 6. ELIGIBILITY (second pass) ──
  {
    id: "eligibility-intro",
    target: '[data-tutorial="eligibility-header"]',
    title: "Step 5: Eligibility (2nd Pass)",
    description: "Stricter review of first-pass included papers. Include or exclude with documented reasons. Only papers included here appear in the final 'Studies included in review' in the PRISMA diagram.",
    page: "/eligibility",
  },
  // ── 7. ALL PAPERS (browse + export) ──
  {
    id: "papers-intro",
    target: '[data-tutorial="papers-header"]',
    title: "Step 6: All Papers",
    description: "Browse and search your entire collection. Filter by decision, eligibility status, or source database.",
    page: "/papers",
  },
  {
    id: "papers-filters",
    target: '[data-tutorial="papers-filters"]',
    title: "Filters & Search",
    description: "Use the Decision and Source dropdowns to filter. Filters are saved per-project — they persist when you navigate away and come back.",
    page: "/papers",
  },
  {
    id: "export-buttons",
    target: '[data-tutorial="export-buttons"]',
    title: "Export",
    description: "Export filtered papers as CSV or BibTeX. The CSV export opens an Elsevier-style field picker where you choose which columns to include. Only the currently filtered papers are exported.",
    page: "/papers",
  },
  // ── 8. DOWNLOADS ──
  {
    id: "downloads-intro",
    target: '[data-tutorial="downloads-header"]',
    title: "Step 7: Downloads",
    description: "Download open access PDFs for your eligible papers. Supports Elsevier (with Scopus API key), arXiv, Unpaywall, and Semantic Scholar.",
    page: "/downloads",
  },
  {
    id: "downloads-viewer",
    target: '[data-tutorial="downloads-table"]',
    title: "PDF Viewer",
    description: "Click 'View' to read papers inline in the browser. Filter by status — Downloaded, No Open Access, or Failed.",
    page: "/downloads",
  },
  // ── 9. MCP SETTINGS ──
  {
    id: "mcp-intro",
    target: '[data-tutorial="mcp-header"]',
    title: "MCP Settings",
    description: "Connect AI agents (Claude, Codex, Copilot, Cursor) to screen papers automatically via the Model Context Protocol. Copy the config snippet for your agent.",
    page: "/mcp-settings",
  },
  // ── 10. FINISH ──
  {
    id: "finish",
    target: null,
    title: "You're All Set!",
    description: "The PRISMA workflow: Settings (configure) → Dashboard (run pipeline) → Screening (1st pass) → Eligibility (2nd pass) → All Papers (export) → Downloads (PDFs). Click 'Take Tour' in the sidebar to restart anytime.",
    page: "/",
  },
];

interface TutorialContextType {
  isActive: boolean;
  currentStep: number;
  step: TutorialStep | null;
  totalSteps: number;
  start: () => void;
  next: () => void;
  back: () => void;
  skip: () => void;
  goToStep: (index: number) => void;
}

const TutorialContext = createContext<TutorialContextType | null>(null);

export function useTutorial() {
  const ctx = useContext(TutorialContext);
  if (!ctx) throw new Error("useTutorial must be used within TutorialProvider");
  return ctx;
}

const STORAGE_KEY = "prisma_tutorial_completed";

export function TutorialProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [isActive, setIsActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [initialized, setInitialized] = useState(false);

  // Check localStorage on mount (client-side only)
  if (typeof window !== "undefined" && !initialized) {
    setInitialized(true);
    if (!localStorage.getItem(STORAGE_KEY)) {
      setIsActive(true);
    }
  }

  const navigateIfNeeded = useCallback(
    (stepIndex: number) => {
      const step = TUTORIAL_STEPS[stepIndex];
      if (step && step.page !== pathname) {
        router.push(step.page);
      }
    },
    [pathname, router]
  );

  const start = useCallback(() => {
    setCurrentStep(0);
    setIsActive(true);
    navigateIfNeeded(0);
  }, [navigateIfNeeded]);

  const next = useCallback(() => {
    const nextIdx = currentStep + 1;
    if (nextIdx >= TUTORIAL_STEPS.length) {
      setIsActive(false);
      localStorage.setItem(STORAGE_KEY, "true");
      return;
    }
    setCurrentStep(nextIdx);
    navigateIfNeeded(nextIdx);
  }, [currentStep, navigateIfNeeded]);

  const back = useCallback(() => {
    const prevIdx = Math.max(0, currentStep - 1);
    setCurrentStep(prevIdx);
    navigateIfNeeded(prevIdx);
  }, [currentStep, navigateIfNeeded]);

  const skip = useCallback(() => {
    setIsActive(false);
    localStorage.setItem(STORAGE_KEY, "true");
  }, []);

  const goToStep = useCallback(
    (index: number) => {
      if (index >= 0 && index < TUTORIAL_STEPS.length) {
        setCurrentStep(index);
        navigateIfNeeded(index);
      }
    },
    [navigateIfNeeded]
  );

  const step = isActive ? TUTORIAL_STEPS[currentStep] ?? null : null;

  return (
    <TutorialContext.Provider
      value={{ isActive, currentStep, step, totalSteps: TUTORIAL_STEPS.length, start, next, back, skip, goToStep }}
    >
      {children}
    </TutorialContext.Provider>
  );
}
