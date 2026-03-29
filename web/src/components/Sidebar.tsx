"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListFilter,
  CheckSquare,
  Library,
  Sliders,
  HardDriveDownload,
  Plug,
} from "lucide-react";

const navItems = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Screening", href: "/screening", icon: ListFilter },
  { label: "Eligibility", href: "/eligibility", icon: CheckSquare },
  { label: "All Papers", href: "/papers", icon: Library },
  { label: "Settings", href: "/settings", icon: Sliders },
  { label: "Downloads", href: "/downloads", icon: HardDriveDownload },
  { label: "MCP Settings", href: "/mcp-settings", icon: Plug },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-bg-surface border-r border-border-glass flex flex-col z-50">
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
          <span className="text-text-muted text-xs font-light">Tool</span>
        </div>
      </div>

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

      {/* Footer */}
      <div className="px-5 py-4 flex items-center justify-between">
        <span className="text-[11px] text-text-muted">v1.1.0 · MIT License</span>
        <a
          href="https://github.com/Black-Lights/prisma-review-tool"
          target="_blank"
          rel="noopener noreferrer"
          className="text-text-muted hover:text-primary"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
          </svg>
        </a>
      </div>
    </aside>
  );
}
