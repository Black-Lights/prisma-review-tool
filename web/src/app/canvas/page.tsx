"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plus, Play, Trash2 } from "lucide-react";
import { nodeTypes, type GraphNodeData, type GraphNodeType } from "@/components/canvas/CustomNode";
import { NodePanel } from "@/components/canvas/NodePanel";

const STORAGE_KEY = "prisma-graph-canvas-v1";

type GraphNode = Node<GraphNodeData>;

function defaultNodeData(title = "Novo nó", type: GraphNodeType = "generic"): GraphNodeData {
  return { title, type, apiKey: "", notes: "", status: "idle", lastOutput: null };
}

function genId() {
  return "n_" + Math.random().toString(36).slice(2, 10);
}

/** Ordena os nós a partir das conexões — quem não tem entrada roda primeiro. */
function topologicalOrder(nodes: GraphNode[], edges: Edge[]): string[] {
  const incoming = new Map(nodes.map((n) => [n.id, 0]));
  for (const e of edges) incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);

  const queue = nodes.filter((n) => (incoming.get(n.id) ?? 0) === 0).map((n) => n.id);
  const visited = new Set<string>();
  const order: string[] = [];

  while (queue.length) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    order.push(id);
    for (const e of edges.filter((e) => e.source === id)) {
      incoming.set(e.target, (incoming.get(e.target) ?? 0) - 1);
      if ((incoming.get(e.target) ?? 0) <= 0 && !visited.has(e.target)) queue.push(e.target);
    }
  }
  for (const n of nodes) if (!visited.has(n.id)) order.push(n.id);
  return order;
}

function CanvasInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const { screenToFlowPosition } = useReactFlow();
  const loadedRef = useRef(false);

  // carrega do localStorage uma vez
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setNodes(parsed.nodes ?? []);
        setEdges(parsed.edges ?? []);
      }
    } catch {
      // sem estado salvo ainda, tudo bem
    } finally {
      loadedRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // salva no localStorage a cada mudança (depois do load inicial)
  useEffect(() => {
    if (!loadedRef.current) return;
    const t = setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ nodes, edges }));
    }, 250);
    return () => clearTimeout(t);
  }, [nodes, edges]);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            type: "smoothstep",
            animated: true,
            style: { stroke: "#7dd3fc", strokeWidth: 2.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#7dd3fc", width: 18, height: 18 },
          },
          eds
        )
      );
    },
    [setEdges]
  );

  const addNode = useCallback(() => {
    const center = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    const id = genId();
    const newNode: GraphNode = {
      id,
      type: "custom",
      position: { x: center.x - 120, y: center.y - 45 },
      data: defaultNodeData(),
    };
    setNodes((nds) => nds.concat(newNode));
    setSelectedId(id);
  }, [screenToFlowPosition, setNodes]);

  const updateNodeData = useCallback(
    (id: string, patch: Partial<GraphNodeData>) => {
      setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
    },
    [setNodes]
  );

  const deleteNode = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
      setSelectedId(null);
    },
    [setNodes, setEdges]
  );

  const runNodes = useCallback(
    async (ids: string[]) => {
      setRunning(true);
      for (const id of ids) {
        updateNodeData(id, { status: "running" });
        await new Promise((r) => setTimeout(r, 700 + Math.random() * 500));
        updateNodeData(id, {
          status: "done",
          lastOutput: `Executado às ${new Date().toLocaleTimeString("pt-BR")}`,
        });
      }
      setRunning(false);
    },
    [updateNodeData]
  );

  const runAll = useCallback(() => {
    if (running) return;
    runNodes(topologicalOrder(nodes, edges));
  }, [running, nodes, edges, runNodes]);

  const runOne = useCallback(
    (id: string) => {
      if (running) return;
      runNodes([id]);
    },
    [running, runNodes]
  );

  const resetAll = useCallback(() => {
    if (!confirm("Apagar todos os nós e conexões?")) return;
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
  }, [setNodes, setEdges]);

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-8">
      {/* toolbar */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border-glass glass rounded-none">
        <h1 className="text-sm font-semibold text-text-primary">Graph Canvas</h1>
        <span className="text-xs text-text-muted">
          {nodes.length} nó(s) · {edges.length} conexão(ões)
        </span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={addNode}
            className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary bg-bg-glass border border-border-glass hover:border-border-glass-hover transition-colors cursor-pointer"
          >
            <Plus size={15} /> Novo nó
          </button>
          <button
            onClick={runAll}
            disabled={running}
            className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium bg-accent-green/15 text-accent-green hover:bg-accent-green/25 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Play size={15} /> {running ? "Executando…" : "Executar tudo"}
          </button>
          <button
            onClick={resetAll}
            className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm font-medium text-accent-red hover:bg-accent-red/10 border border-transparent hover:border-accent-red/30 transition-colors cursor-pointer"
          >
            <Trash2 size={15} /> Limpar
          </button>
        </div>
      </div>

      {/* canvas + painel */}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            colorMode="dark"
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(125,211,252,0.15)" />
            <Controls className="!bg-bg-surface !border !border-border-glass !rounded-lg overflow-hidden" />
            <MiniMap
              className="!bg-bg-surface !border !border-border-glass !rounded-lg"
              maskColor="rgba(10,14,26,0.7)"
              nodeColor="#7dd3fc33"
            />
          </ReactFlow>
        </div>

        <div className="p-4">
          <NodePanel node={selectedNode} onChange={updateNodeData} onRun={runOne} onDelete={deleteNode} />
        </div>
      </div>
    </div>
  );
}

export default function CanvasPage() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}
