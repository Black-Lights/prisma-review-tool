"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle, X } from "lucide-react";
import { TutorialProvider } from "@/context/TutorialContext";
import { API_BASE, ApiError } from "@/lib/api";
import { startRealtimeSync } from "@/lib/realtime";

/**
 * A 409 with a plain-text detail from a query means the active project is
 * unusable (stale or invalid marker, missing or broken config.yaml). Every
 * config-dependent screen would fail, so the user is sent to Projects with
 * the server's explanation.
 */
interface WorkspaceAlert {
  message: string | null;
  clear: () => void;
}

const WorkspaceAlertContext = createContext<WorkspaceAlert>({ message: null, clear: () => {} });

export const useWorkspaceAlert = () => useContext(WorkspaceAlertContext);

function WorkspaceGuard({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const pathRef = useRef(pathname);
  const [message, setMessage] = useState<string | null>(null);
  const clear = useCallback(() => setMessage(null), []);

  useEffect(() => {
    pathRef.current = pathname;
  }, [pathname]);

  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((event) => {
        if (event.type !== "updated" || event.action.type !== "error") return;
        const err = event.action.error;
        if (!(err instanceof ApiError) || err.status !== 409 || typeof err.detail !== "string") return;
        setMessage(err.detail);
        if (pathRef.current !== "/projects") router.push("/projects");
      }),
    [queryClient, router],
  );

  return (
    <WorkspaceAlertContext.Provider value={{ message, clear }}>
      {message && (
        <div
          role="alert"
          className="fixed top-4 left-72 right-8 z-[60] glass-elevated border-l-4 border-l-accent-amber px-4 py-3 flex items-start gap-3 shadow-xl"
        >
          <AlertTriangle size={18} className="text-accent-amber shrink-0 mt-0.5" />
          <div className="text-sm flex-1 min-w-0">
            <p className="font-semibold text-text-primary">No usable active project</p>
            <p className="text-text-secondary break-words">{message}</p>
            <p className="text-text-muted text-xs mt-1">Switch to a project below (or create one) to continue.</p>
          </div>
          <button
            type="button"
            onClick={clear}
            aria-label="Dismiss"
            className="text-text-muted hover:text-text-primary p-1 cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>
      )}
      {children}
    </WorkspaceAlertContext.Provider>
  );
}

/**
 * One SSE subscription per visible tab; each event refreshes only the query
 * keys of the areas that changed on disk (see lib/realtime.ts).
 */
function RealtimeSync() {
  const queryClient = useQueryClient();
  const { clear } = useWorkspaceAlert();
  useEffect(
    () =>
      startRealtimeSync({
        url: `${API_BASE}/api/events`,
        onRefresh: (plan) => {
          if (plan.kind === "reset") {
            clear();
            queryClient.resetQueries();
          } else if (plan.kind === "all") {
            queryClient.invalidateQueries();
          } else if (plan.keys.length) {
            queryClient.invalidateQueries({ predicate: (q) => plan.keys.includes(String(q.queryKey[0])) });
          }
        },
      }),
    [queryClient, clear],
  );
  return null;
}

// Client errors (4xx) do not get better on retry.
const retryQuery = (failureCount: number, error: unknown) =>
  !(error instanceof ApiError && error.status < 500) && failureCount < 1;

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: retryQuery },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <WorkspaceGuard>
        <RealtimeSync />
        <TutorialProvider>{children}</TutorialProvider>
      </WorkspaceGuard>
    </QueryClientProvider>
  );
}
