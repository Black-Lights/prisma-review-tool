"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  ListFilter,
  CheckSquare,
  Library,
  Sliders,
  HardDriveDownload,
  Plug,
  HelpCircle,
  FolderOpen,
  ChevronRight,
  Info,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchActiveProject } from "@/lib/api";
import { useTutorial } from "@/context/TutorialContext";

const navItems = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Screening", href: "/screening", icon: ListFilter },
  { label: "Eligibility", href: "/eligibility", icon: CheckSquare },
  { label: "All Papers", href: "/papers", icon: Library },
  { label: "Settings", href: "/settings", icon: Sliders },
  { label: "Downloads", href: "/downloads", icon: HardDriveDownload },
  { label: "MCP Settings", href: "/mcp-settings", icon: Plug },
];

const APP_VERSION = "1.5.1";

export function Sidebar() {
  const pathname = usePathname();
  const { start } = useTutorial();
  const [showAbout, setShowAbout] = useState(false);
  const { data: activeProject } = useQuery({
    queryKey: ["active-project"],
    queryFn: fetchActiveProject,
  });

  return (
    <aside data-tutorial="sidebar" className="fixed left-0 top-0 h-screen w-64 bg-bg-surface border-r border-border-glass flex flex-col z-50">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-6">
        <svg
          width="32"
          height="32"
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="shrink-0"
        >
          <path
            d="M16 2L28 10V22L16 30L4 22V10L16 2Z"
            fill="rgba(125,211,252,0.15)"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-primary"
          />
          <path
            d="M16 2L28 10L16 18L4 10L16 2Z"
            fill="rgba(125,211,252,0.25)"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
          <path
            d="M16 18V30"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-primary"
          />
        </svg>
        <div className="flex flex-col leading-tight">
          <span className="text-text-primary font-bold text-base tracking-tight">
            PRISMA Review
          </span>
          <span className="text-text-muted text-xs font-light">v{APP_VERSION}</span>
        </div>
      </div>

      {/* Active project indicator */}
      {activeProject?.active && (
        <Link
          href="/projects"
          className="mx-3 mb-2 px-3 py-2 rounded-lg bg-bg-glass border border-border-glass hover:border-border-glass-hover flex items-center gap-2 group transition-colors"
        >
          <FolderOpen size={14} className="text-primary shrink-0" />
          <span className="text-xs text-text-secondary truncate flex-1">
            {activeProject.display_name || activeProject.active}
          </span>
          <ChevronRight size={12} className="text-text-muted group-hover:text-primary shrink-0" />
        </Link>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-3 mt-2 space-y-1">
        {navItems.map(({ label, href, icon: Icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 h-[44px] pl-4 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary-dim text-primary"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-glass"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer — Take Tour + About + GitHub */}
      <div className="px-3 pb-4 space-y-1">
        <button
          onClick={start}
          className="flex items-center gap-2 w-full h-[38px] pl-4 rounded-lg text-xs font-medium text-text-muted hover:text-primary hover:bg-bg-glass transition-colors cursor-pointer"
        >
          <HelpCircle size={16} /> Take Tour
        </button>
        <div className="flex items-center justify-between pl-4 pr-2 h-[32px]">
          <button
            onClick={() => setShowAbout(true)}
            className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-primary transition-colors cursor-pointer"
          >
            <Info size={12} />
            v{APP_VERSION} · About
          </button>
          <a
            href="https://github.com/Black-Lights/prisma-review-tool"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-muted hover:text-primary"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
            </svg>
          </a>
        </div>
      </div>

      {/* About Modal */}
      {showAbout && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center"
          onClick={(e) => { if (e.target === e.currentTarget) setShowAbout(false); }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative glass-elevated p-0 w-full max-w-md mx-4 shadow-2xl" style={{ animation: "modalIn 0.2s ease-out" }}>
            <div className="p-6 space-y-4">
              {/* Logo + Title */}
              <div className="flex items-center gap-4">
                <svg width="40" height="40" viewBox="0 0 32 32" fill="none" className="shrink-0">
                  <path d="M16 2L28 10V22L16 30L4 22V10L16 2Z" fill="rgba(125,211,252,0.15)" stroke="#7dd3fc" strokeWidth="1.5" />
                  <path d="M16 2L28 10L16 18L4 10L16 2Z" fill="rgba(125,211,252,0.25)" stroke="#7dd3fc" strokeWidth="1" />
                  <path d="M16 18V30" stroke="#7dd3fc" strokeWidth="1.5" />
                </svg>
                <div>
                  <h3 className="text-lg font-bold text-text-primary">PRISMA Review Tool</h3>
                  <p className="text-sm text-text-muted">v{APP_VERSION}</p>
                </div>
              </div>

              {/* Description */}
              <p className="text-sm text-text-secondary leading-relaxed">
                Automated systematic literature review following the PRISMA 2020 guidelines
                (Page et al., BMJ 2021;372:n71). Search academic databases, deduplicate,
                screen with keyword rules and AI, generate PRISMA flow diagrams, and export results.
              </p>

              {/* Details */}
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1.5 border-b border-border-glass">
                  <span className="text-text-muted">Created by</span>
                  <span className="text-text-primary">Mohammad Ammar Mughees</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border-glass">
                  <span className="text-text-muted">License</span>
                  <span className="text-text-primary">MIT</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border-glass">
                  <span className="text-text-muted">Python</span>
                  <span className="text-text-primary">3.10+</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border-glass">
                  <span className="text-text-muted">Node.js</span>
                  <span className="text-text-primary">18+</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border-glass">
                  <span className="text-text-muted">PRISMA Standard</span>
                  <span className="text-text-primary">PRISMA 2020 (Page et al., 2021)</span>
                </div>
              </div>

              {/* Citation */}
              <div>
                <p className="text-xs text-text-muted mb-1.5">Cite as:</p>
                <div className="bg-bg-glass rounded-lg p-3 text-[11px] text-text-secondary font-mono leading-relaxed select-all">
                  Mughees, M. A. (2026). PRISMA Review Tool: AI-Assisted Systematic Literature Review [Software]. https://github.com/Black-Lights/prisma-review-tool
                </div>
              </div>

              {/* Links */}
              <div className="flex gap-3">
                <a
                  href="https://github.com/Black-Lights/prisma-review-tool"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 text-center px-3 py-2 rounded-lg text-xs font-medium bg-bg-glass text-text-secondary border border-border-glass hover:text-text-primary hover:border-border-glass-hover transition-colors"
                >
                  GitHub
                </a>
                <a
                  href="https://github.com/Black-Lights/prisma-review-tool/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 text-center px-3 py-2 rounded-lg text-xs font-medium bg-bg-glass text-text-secondary border border-border-glass hover:text-text-primary hover:border-border-glass-hover transition-colors"
                >
                  Report Issue
                </a>
                <a
                  href="https://github.com/Black-Lights/prisma-review-tool/blob/main/CHANGELOG.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 text-center px-3 py-2 rounded-lg text-xs font-medium bg-bg-glass text-text-secondary border border-border-glass hover:text-text-primary hover:border-border-glass-hover transition-colors"
                >
                  Changelog
                </a>
              </div>
            </div>

            {/* Close */}
            <div className="flex justify-end px-6 py-4 border-t border-border-glass">
              <button
                onClick={() => setShowAbout(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-primary/15 text-primary hover:bg-primary/25 transition-colors"
              >
                Close
              </button>
            </div>
          </div>

          <style jsx>{`
            @keyframes modalIn {
              from { opacity: 0; transform: scale(0.95) translateY(8px); }
              to { opacity: 1; transform: scale(1) translateY(0); }
            }
          `}</style>
        </div>
      )}
    </aside>
  );
}
