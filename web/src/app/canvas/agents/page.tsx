"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Play, RotateCcw, AlertTriangle, Terminal, CheckCircle2 } from "lucide-react";
import { nodeTypes, type GraphNodeData, type GraphNodeStatus } from "@/components/canvas/CustomNode";
import {
  listAssistants,
  getGraphStructure,
  createThread,
  getThreadState,
  streamRun,
} from "@/lib/langgraph";

type GraphNode = Node<GraphNodeData>;

const NODE_W = 240;
const GAP_X = 320;

/** Layout horizontal simples: ordena por dependência e espalha da esquerda pra direita. */
function layoutNodes(nodeIds: string[], edges: { source: string; target: string }[]): Record<string, { x: number; y: number }> {
  const incoming = new Map(nodeIds.map((id) => [id, 0]));
  for (const e of edges) if (incoming.has(e.target)) incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);

  const layers: string[][] = [];
  const remaining = new Set(nodeIds);
  const inc = new Map(incoming);

  while (remaining.size) {
    const layer = [...remaining].filter((id) => (inc.get(id) ?? 0) === 0);
    if (layer.length === 0) {
      layers.push([...remaining]);
      break;
    }
    layers.push(layer);
    for (const id of layer) {
      remaining.delete(id);
      for (const e of edges) {
        if (e.source === id && inc.has(e.target)) inc.set(e.target, (inc.get(e.target) ?? 0) - 1);
      }
    }
  }

  const positions: Record<string, { x: number; y: number }> = {};
  layers.forEach((layer, col) => {
    layer.forEach((id, row) => {
      positions[id] = { x: col * GAP_X, y: row * 140 };
    });
  });
  return positions;
}

function CanvasInner() {
  const [assistantId, setAssistantId] = useState<string | null>(null);
  const [allNodeIds, setAllNodeIds] = useState<string[]>([]);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [nextNodeId, setNextNodeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);

  // carrega o grafo real do servidor local do LangGraph
  useEffect(() => {
    (async () => {
      try {
        const assistants = await listAssistants();
        const assistant = assistants.find((a) => a.graph_id === "prisma_agents") ?? assistants[0];
        if (!assistant) throw new Error("Nenhum assistant encontrado — o servidor langgraph dev está rodando?");
        setAssistantId(assistant.assistant_id);

        const structure = await getGraphStructure(assistant.assistant_id);
        const realNodeIds = structure.nodes.map((n) => n.id).filter((id) => id !== "__start__" && id !== "__end__");
        setAllNodeIds(realNodeIds);

        const positions = layoutNodes(realNodeIds, structure.edges);
        setNodes(
          realNodeIds.map((id) => ({
            id,
            type: "custom",
            position: positions[id] ?? { x: 0, y: 0 },
            data: { title: id, type: "ai", status: "idle" as GraphNodeStatus, notes: "", lastOutput: null },
          }))
        );
        setEdges(
          structure.edges
            .filter((e) => e.source !== "__start__" && e.target !== "__end__")
            .map((e) => ({
              id: `${e.source}->${e.target}`,
              source: e.source,
              target: e.target,
              type: "smoothstep",
              animated: true,
              style: { stroke: "#7dd3fc", strokeWidth: 2.5 },
              markerEnd: { type: MarkerType.ArrowClosed, color: "#7dd3fc", width: 18, height: 18 },
            }))
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  const setNodeStatus = useCallback((id: string, patch: Partial<GraphNodeData>) => {
    setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
  }, []);

  const refreshNext = useCallback(
    async (tId: string) => {
      const state = await getThreadState(tId);
      const next = state.next?.[0] ?? null;
      setNextNodeId(next);
      if (next) setNodeStatus(next, { status: "waiting" });
      if (!next) setFinished(true);
    },
    [setNodeStatus]
  );

  const step = useCallback(
    async (isFirst: boolean) => {
      if (!assistantId || busy) return;
      setBusy(true);
      setError(null);
      try {
        let tId = threadId;
        if (isFirst) {
          const thread = await createThread();
          tId = thread.thread_id;
          setThreadId(tId);
        } else if (nextNodeId) {
          setNodeStatus(nextNodeId, { status: "running" });
        }
        if (!tId) throw new Error("Sem thread ativa");

        const input = isFirst
          ? { project_name: "PRISMA review", log: [], papers_found: 0, papers_deduped: 0, papers_screened: 0, papers_eligible: 0 }
          : null;

        await streamRun(tId, assistantId, input, allNodeIds, (evt) => {
          if (evt.event === "updates") {
            const data = evt.data as Record<string, unknown>;
            for (const key of Object.keys(data)) {
              if (key === "__interrupt__") continue;
              const nodeOutput = data[key] as { log?: string[] };
              const lastLine = nodeOutput?.log?.[nodeOutput.log.length - 1];
              setNodeStatus(key, { status: "done", lastOutput: lastLine ?? "concluído" });
              if (lastLine) setLog((l) => [...l, lastLine]);
            }
          }
        });

        await refreshNext(tId);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [assistantId, busy, threadId, nextNodeId, allNodeIds, setNodeStatus, refreshNext]
  );

  const reset = useCallback(() => {
    setThreadId(null);
    setNextNodeId(null);
    setFinished(false);
    setLog([]);
    setError(null);
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, status: "idle" as GraphNodeStatus, lastOutput: null } })));
  }, []);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-8">
      <div className="flex items-center gap-4 px-6 py-3 border-b border-border-glass glass rounded-none">
        <h1 className="text-sm font-semibold text-text-primary shrink-0">Agentes PRISMA — LangGraph</h1>

        {/* stepper compacto de progresso */}
        <div className="flex items-center gap-1.5">
          {nodes.map((n, i) => (
            <div key={n.id} className="flex items-center gap-1.5">
              <div
                className="w-2 h-2 rounded-full transition-colors"
                style={{
                  background:
                    n.data.status === "done"
                      ? "#34d399"
                      : n.data.status === "running"
                      ? "#fbbf24"
                      : n.data.status === "waiting"
                      ? "#c084fc"
                      : "rgba(125,211,252,0.2)",
                }}
                title={n.data.title}
              />
              {i < nodes.length - 1 && <div className="w-4 h-px bg-border-glass" />}
            </div>
          ))}
        </div>

        <span className="text-xs text-text-muted">
          {!threadId
            ? "pronto pra iniciar"
            : finished
            ? "execução concluída"
            : `aguardando: ${nextNodeId ?? "…"}`}
        </span>
        <div className="ml-auto flex gap-2">
          {!threadId && (
            <button
              onClick={() => step(true)}
              disabled={busy || !assistantId}
              className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium bg-accent-green/15 text-accent-green hover:bg-accent-green/25 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Play size={15} /> Iniciar execução
            </button>
          )}
          {threadId && !finished && (
            <button
              onClick={() => step(false)}
              disabled={busy}
              className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium bg-accent-purple/15 text-accent-purple hover:bg-accent-purple/25 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Play size={15} /> {busy ? "Rodando…" : `Continuar (${nextNodeId})`}
            </button>
          )}
          {threadId && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary bg-bg-glass border border-border-glass transition-colors cursor-pointer"
            >
              <RotateCcw size={15} /> Nova thread
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-6 py-2 bg-accent-red/10 text-accent-red text-sm border-b border-accent-red/20">
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 relative">
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} colorMode="dark" fitView proOptions={{ hideAttribution: true }}>
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(125,211,252,0.15)" />
            <Controls className="!bg-bg-surface !border !border-border-glass !rounded-lg overflow-hidden" />
            <MiniMap
              className="!bg-bg-surface !border !border-border-glass !rounded-lg"
              maskColor="rgba(10,14,26,0.7)"
              nodeColor="#7dd3fc33"
            />
          </ReactFlow>
        </div>

        <aside className="w-[360px] shrink-0 glass p-5 m-4 overflow-y-auto">
          <div className="flex items-center gap-2 mb-4">
            <Terminal size={14} className="text-primary" />
            <h2 className="text-xs uppercase tracking-wide text-text-muted">Log de execução</h2>
            {log.length > 0 && (
              <span className="ml-auto text-[10px] text-text-muted bg-bg-glass px-2 py-0.5 rounded-full">
                {log.length} evento(s)
              </span>
            )}
          </div>

          {log.length === 0 ? (
            <p className="text-sm text-text-muted">Nada rodou ainda — clique em &quot;Iniciar execução&quot;.</p>
          ) : (
            <ul className="space-y-2.5">
              {log.map((line, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-[13px] text-text-secondary rounded-lg px-3 py-2.5"
                  style={{ background: "rgba(15,21,36,0.5)", border: "1px solid rgba(125,211,252,0.08)" }}
                >
                  <CheckCircle2 size={13} className="text-accent-green shrink-0 mt-0.5" />
                  <span className="leading-snug">{line}</span>
                </li>
              ))}
            </ul>
          )}

          {finished && (
            <div className="mt-4 flex items-center gap-2 text-xs text-accent-green bg-accent-green/10 rounded-lg px-3 py-2.5">
              <CheckCircle2 size={14} /> Pipeline concluído — todos os agentes rodaram.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export default function AgentsCanvasPage() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}
