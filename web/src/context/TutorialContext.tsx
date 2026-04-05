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
  // Dashboard
  {
    id: "welcome",
    target: null,
    title: "Welcome to PRISMA Review Tool!",
    description: "Let's take a quick tour of the app. We'll walk you through the key features so you can get started with your systematic literature review.",
    page: "/",
  },
  {
    id: "sidebar",
    target: '[data-tutorial="sidebar"]',
    title: "Navigation Sidebar",
    description: "Navigate between different sections. Dashboard shows your overview, Screening and Eligibility are where you review papers.",
    page: "/",
  },
  {
    id: "stat-cards",
    target: '[data-tutorial="stat-cards"]',
    title: "Pipeline Statistics",
    description: "These show your pipeline progress at a glance -- from initial search results to final eligible papers.",
    page: "/",
  },
  {
    id: "prisma-diagram",
    target: '[data-tutorial="prisma-diagram"]',
    title: "PRISMA 2020 Flow Diagram",
    description: "Your PRISMA 2020 flow diagram updates automatically as you screen papers. Click Download PNG to save it for your thesis.",
    page: "/",
  },
  {
    id: "pipeline-stepper",
    target: '[data-tutorial="pipeline-stepper"]',
    title: "Pipeline Steps",
    description: "Run the full pipeline here -- search databases, deduplicate, and screen papers. Green checkmarks show completed steps.",
    page: "/",
  },
  {
    id: "run-all",
    target: '[data-tutorial="run-all"]',
    title: "Run All Button",
    description: "Click this to start the pipeline. It searches academic databases, removes duplicates, and applies your keyword screening rules -- all in the background.",
    page: "/",
  },
  // Screening
  {
    id: "screening-intro",
    target: '[data-tutorial="screening-header"]',
    title: "Screening Page",
    description: 'This is where you review papers that need manual decisions. Papers marked "Maybe" by keyword screening need your input.',
    page: "/screening",
  },
  {
    id: "filter-pills",
    target: '[data-tutorial="filter-pills"]',
    title: "Filter Papers",
    description: "Filter papers by their current status -- Maybe (needs review), Included, or Excluded.",
    page: "/screening",
  },
  {
    id: "paper-card",
    target: '[data-tutorial="paper-card"]',
    title: "Paper Card",
    description: "Each card shows the paper's title, authors, year, and abstract. Click the title to see full details. Use Show More to expand the abstract.",
    page: "/screening",
  },
  {
    id: "decision-buttons",
    target: '[data-tutorial="decision-controls"]',
    title: "Make Decisions",
    description: "Click Include to keep a paper in your review, or Exclude to remove it. Add a brief reason to document your decision.",
    page: "/screening",
  },
  // All Papers
  {
    id: "papers-intro",
    target: '[data-tutorial="papers-header"]',
    title: "All Papers",
    description: "Browse and search all papers in your collection. Use filters to find specific papers.",
    page: "/papers",
  },
  {
    id: "papers-filters",
    target: '[data-tutorial="papers-filters"]',
    title: "Search & Filters",
    description: "Search by keywords, filter by decision status or source database. Export your results as CSV or BibTeX.",
    page: "/papers",
  },
  // Settings
  {
    id: "settings-intro",
    target: '[data-tutorial="settings-header"]',
    title: "Settings",
    description: "Configure your entire review protocol here -- search queries, screening keywords, and database sources.",
    page: "/settings",
  },
  {
    id: "search-queries",
    target: '[data-tutorial="search-queries"]',
    title: "Search Queries",
    description: "Define Boolean search queries. Use AND/OR operators to combine terms. Each query searches all selected databases.",
    page: "/settings",
  },
  {
    id: "screening-rules",
    target: '[data-tutorial="screening-rules"]',
    title: "Screening Rules",
    description: "Set include and exclude keywords. Papers matching enough include keywords (and no exclude keywords) pass the first screening.",
    page: "/settings",
  },
  // Projects
  {
    id: "projects-intro",
    target: '[data-tutorial="projects-header"]',
    title: "Projects",
    description: "Manage multiple literature reviews. Create, switch, duplicate, or export projects — each with its own config and data.",
    page: "/projects",
  },
  // Eligibility
  {
    id: "eligibility-intro",
    target: '[data-tutorial="eligibility-header"]',
    title: "Eligibility Screening",
    description: "Second-pass screening for stricter criteria. Review first-pass included papers and apply your domain-specific eligibility rules to narrow down to the most relevant studies.",
    page: "/eligibility",
  },
  // Downloads
  {
    id: "downloads-intro",
    target: '[data-tutorial="downloads-header"]',
    title: "Downloads",
    description: "Download open access PDFs for your eligible papers. Supports Elsevier (institutional access), arXiv, Unpaywall, and Semantic Scholar.",
    page: "/downloads",
  },
  {
    id: "downloads-viewer",
    target: '[data-tutorial="downloads-table"]',
    title: "PDF Viewer",
    description: "Click View to read papers inline. Filter by status — Downloaded, No Open Access, or Failed.",
    page: "/downloads",
  },
  // Export (on papers page)
  {
    id: "export-buttons",
    target: '[data-tutorial="export-buttons"]',
    title: "Export Papers",
    description: "Export filtered papers as CSV or BibTeX. Choose which fields to include — like Scopus export. Exports only the papers matching your current filters.",
    page: "/papers",
  },
  // MCP Settings
  {
    id: "mcp-intro",
    target: '[data-tutorial="mcp-header"]',
    title: "MCP Settings",
    description: "Connect AI agents like Claude, Codex, or Copilot to screen papers automatically via the Model Context Protocol.",
    page: "/mcp-settings",
  },
  // Finish
  {
    id: "finish",
    target: null,
    title: "You're All Set!",
    description: "Start by configuring your search queries in Settings, then run the pipeline from the Dashboard. Happy reviewing!",
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
