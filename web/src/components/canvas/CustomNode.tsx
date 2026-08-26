"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Globe, Terminal, Sparkles, Box, KeyRound, Loader2, CheckCircle2, XCircle, PauseCircle } from "lucide-react";

export type GraphNodeStatus = "idle" | "waiting" | "running" | "done" | "error";
export type GraphNodeType = "generic" | "http" | "script" | "ai";

export type GraphNodeData = {
  title: string;
  type: GraphNodeType;
  apiKey?: string;
  notes?: string;
  status: GraphNodeStatus;
  lastOutput?: string | null;
};

const TYPE_META: Record<GraphNodeType, { icon: typeof Box; label: string; color: string }> = {
  generic: { icon: Box, label: "Genérico", color: "#7dd3fc" },
  http: { icon: Globe, label: "HTTP Request", color: "#34d399" },
  script: { icon: Terminal, label: "Script", color: "#fbbf24" },
  ai: { icon: Sparkles, label: "IA / LLM", color: "#c084fc" },
};

const STATUS_META: Record<GraphNodeStatus, { ring: string; label: string; badgeBg: string }> = {
  idle: { ring: "rgba(125, 211, 252, 0.18)", label: "Ocioso", badgeBg: "rgba(125, 211, 252, 0.1)" },
  waiting: { ring: "#c084fc", label: "Aguardando aprovação", badgeBg: "rgba(192, 132, 252, 0.15)" },
  running: { ring: "#fbbf24", label: "Executando…", badgeBg: "rgba(251, 191, 36, 0.15)" },
  done: { ring: "#34d399", label: "Concluído", badgeBg: "rgba(52, 211, 153, 0.15)" },
  error: { ring: "#f87171", label: "Erro", badgeBg: "rgba(248, 113, 113, 0.15)" },
};

function CustomNodeImpl({ data, selected }: NodeProps & { data: GraphNodeData }) {
  const meta = TYPE_META[data.type] ?? TYPE_META.generic;
  const status = STATUS_META[data.status];
  const Icon = meta.icon;
  const isActive = data.status === "running" || data.status === "waiting";

  return (
    <div
      className="relative w-[250px] rounded-2xl overflow-hidden select-none transition-shadow duration-300"
      style={{
        background: "linear-gradient(180deg, rgba(15,21,36,0.92) 0%, rgba(10,14,26,0.96) 100%)",
        backdropFilter: "blur(20px)",
        border: `1px solid ${selected ? "#7dd3fc" : status.ring}`,
        boxShadow: selected
          ? `0 0 0 3px rgba(125,211,252,0.15), 0 8px 30px rgba(0,0,0,0.5)`
          : isActive
          ? `0 0 28px ${status.ring}40, 0 8px 24px rgba(0,0,0,0.4)`
          : "0 4px 16px rgba(0,0,0,0.35)",
      }}
    >
      {/* glow ambiental sutil no topo, colorido pelo tipo do nó */}
      <div
        className="absolute -top-10 left-1/2 -translate-x-1/2 w-40 h-20 rounded-full opacity-25 pointer-events-none blur-2xl"
        style={{ background: meta.color }}
      />

      <Handle
        type="target"
        position={Position.Left}
        className="!w-3.5 !h-3.5 !border-2 !transition-transform hover:!scale-125"
        style={{ background: "#0a0e1a", borderColor: meta.color }}
      />

      {/* header */}
      <div className="relative flex items-center gap-2.5 px-3.5 py-3 border-b border-white/5">
        <div
          className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0"
          style={{
            background: `linear-gradient(135deg, ${meta.color}33, ${meta.color}14)`,
            color: meta.color,
            boxShadow: `inset 0 0 0 1px ${meta.color}33`,
          }}
        >
          <Icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-text-primary truncate leading-tight">{data.title}</div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted font-medium">{meta.label}</div>
        </div>
        <StatusIcon status={data.status} />
      </div>

      {/* body */}
      <div className="relative px-3.5 py-3 space-y-2">
        <span
          className="inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-1 rounded-full"
          style={{ background: status.badgeBg, color: status.ring }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: status.ring }} />
          {status.label}
        </span>

        {data.apiKey ? (
          <div className="flex items-center gap-1.5 text-[11px] text-accent-green">
            <KeyRound size={11} /> API key configurada
          </div>
        ) : (
          <div className="text-[11px] text-text-muted">Sem credencial configurada</div>
        )}

        {data.lastOutput && (
          <div
            className="text-[11px] text-text-secondary truncate rounded-md px-2 py-1.5"
            style={{ background: "rgba(0,0,0,0.25)" }}
            title={data.lastOutput}
          >
            {data.lastOutput}
          </div>
        )}
      </div>

      {/* barra de progresso indeterminada enquanto roda */}
      {data.status === "running" && (
        <div className="relative h-[3px] w-full overflow-hidden" style={{ background: "rgba(251,191,36,0.15)" }}>
          <div className="absolute inset-y-0 w-1/3 rounded-full progress-sweep" style={{ background: status.ring }} />
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!w-3.5 !h-3.5 !border-2 !transition-transform hover:!scale-125"
        style={{ background: "#0a0e1a", borderColor: meta.color }}
      />

      <style jsx>{`
        .progress-sweep {
          animation: sweep 1.1s ease-in-out infinite;
        }
        @keyframes sweep {
          0% {
            left: -33%;
          }
          100% {
            left: 100%;
          }
        }
      `}</style>
    </div>
  );
}

function StatusIcon({ status }: { status: GraphNodeStatus }) {
  if (status === "waiting") return <PauseCircle size={15} className="text-accent-purple shrink-0" />;
  if (status === "running") return <Loader2 size={15} className="animate-spin text-accent-amber shrink-0" />;
  if (status === "done") return <CheckCircle2 size={15} className="text-accent-green shrink-0" />;
  if (status === "error") return <XCircle size={15} className="text-accent-red shrink-0" />;
  return null;
}

export const CustomNode = memo(CustomNodeImpl);
export const nodeTypes = { custom: CustomNode };
