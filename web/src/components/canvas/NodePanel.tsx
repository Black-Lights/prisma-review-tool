"use client";

import type { Node } from "@xyflow/react";
import type { GraphNodeData, GraphNodeType } from "./CustomNode";
import { Play, Trash2, Layers, KeyRound, FileText, Sparkles } from "lucide-react";

const TYPE_OPTIONS: { value: GraphNodeType; label: string }[] = [
  { value: "generic", label: "Genérico" },
  { value: "http", label: "HTTP Request" },
  { value: "script", label: "Script" },
  { value: "ai", label: "IA / LLM" },
];

export function NodePanel({
  node,
  onChange,
  onRun,
  onDelete,
}: {
  node: Node<GraphNodeData> | null;
  onChange: (id: string, patch: Partial<GraphNodeData>) => void;
  onRun: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (!node) {
    return (
      <aside className="w-[360px] shrink-0 glass p-6 flex flex-col items-center text-center gap-3 justify-center">
        <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-primary-dim">
          <Layers size={20} className="text-primary" />
        </div>
        <h2 className="text-sm font-semibold text-text-primary">Nenhum nó selecionado</h2>
        <p className="text-xs text-text-muted leading-relaxed">
          Clique num nó pra configurar, ou arraste da bolinha da direita de um nó até a da esquerda de outro pra conectar.
        </p>
      </aside>
    );
  }

  const data = node.data;

  return (
    <aside className="w-[360px] shrink-0 glass overflow-y-auto">
      <div className="px-5 py-4 border-b border-border-glass flex items-center gap-2">
        <Sparkles size={14} className="text-primary" />
        <h2 className="text-xs uppercase tracking-wide text-text-muted">Propriedades do nó</h2>
      </div>

      <div className="p-5 space-y-5">
        <Field label="Nome" icon={<FileText size={11} />}>
          <input
            className="glass-input w-full text-sm"
            value={data.title}
            onChange={(e) => onChange(node.id, { title: e.target.value })}
          />
        </Field>

        <Field label="Tipo" icon={<Layers size={11} />}>
          <select
            className="glass-input w-full text-sm"
            value={data.type}
            onChange={(e) => onChange(node.id, { type: e.target.value as GraphNodeType })}
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="API Key" icon={<KeyRound size={11} />}>
          <input
            type="password"
            className="glass-input w-full text-sm font-mono"
            placeholder="cole a chave aqui"
            value={data.apiKey ?? ""}
            onChange={(e) => onChange(node.id, { apiKey: e.target.value })}
          />
        </Field>

        <Field label="Notas / configuração" icon={<FileText size={11} />}>
          <textarea
            className="glass-input w-full text-sm font-mono min-h-[90px] resize-y"
            placeholder="qualquer anotação livre sobre esse nó"
            value={data.notes ?? ""}
            onChange={(e) => onChange(node.id, { notes: e.target.value })}
          />
        </Field>

        {data.lastOutput && (
          <Field label="Última saída" icon={<Sparkles size={11} />}>
            <div className="glass-input w-full text-xs font-mono min-h-[50px] whitespace-pre-wrap" style={{ background: "rgba(0,0,0,0.25)" }}>
              {data.lastOutput}
            </div>
          </Field>
        )}

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => onRun(node.id)}
            className="flex-1 flex items-center justify-center gap-1.5 h-10 rounded-lg text-sm font-semibold bg-accent-green/15 text-accent-green hover:bg-accent-green/25 transition-colors cursor-pointer"
          >
            <Play size={14} /> Rodar
          </button>
          <button
            onClick={() => onDelete(node.id)}
            className="flex-1 flex items-center justify-center gap-1.5 h-10 rounded-lg text-sm font-semibold bg-accent-red/15 text-accent-red hover:bg-accent-red/25 transition-colors cursor-pointer"
          >
            <Trash2 size={14} /> Excluir
          </button>
        </div>
      </div>
    </aside>
  );
}

function Field({ label, icon, children }: { label: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-text-muted mb-1.5">
        {icon}
        {label}
      </label>
      {children}
    </div>
  );
}
