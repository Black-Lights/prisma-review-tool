"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { TutorialProvider } from "@/context/TutorialContext";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Subscribes once to the API's SSE stream and invalidates all React Query
 * caches whenever shared disk state changes (e.g. a pipeline run or project
 * switch driven by the MCP server). Active queries refetch automatically, so
 * every screen reflects out-of-process changes in real time without polling.
 */
function RealtimeSync() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const es = new EventSource(`${API}/api/events`);
    es.onmessage = () => {
      queryClient.invalidateQueries();
    };
    // EventSource reconnects on its own after transient errors; nothing to do.
    return () => es.close();
  }, [queryClient]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <RealtimeSync />
      <TutorialProvider>{children}</TutorialProvider>
    </QueryClientProvider>
  );
}
