"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderOpen,
  Plus,
  Copy,
  Trash2,
  Download,
  Upload,
  ArrowRightLeft,
  Search,
  Database,
  Filter,
  CheckCircle2,
} from "lucide-react";
import GlassCard from "@/components/GlassCard";
import Modal from "@/components/Modal";
import {
  fetchProjects,
  createProject,
  switchProject,
  deleteProject,
  duplicateProject,
  exportProject,
  importProject,
  Project,
} from "@/lib/api";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<string | null>(null);
  const [duplicateName, setDuplicateName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
  });

  const projects = data?.projects ?? [];

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["projects"] });
    queryClient.invalidateQueries({ queryKey: ["active-project"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
    queryClient.invalidateQueries({ queryKey: ["pipeline-progress"] });
  };

  const createMutation = useMutation({
    mutationFn: (name: string) => createProject(name),
    onSuccess: () => {
      invalidateAll();
      setShowCreateModal(false);
      setNewProjectName("");
    },
  });

  const switchMutation = useMutation({
    mutationFn: (name: string) => switchProject(name),
    onSuccess: invalidateAll,
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => deleteProject(name),
    onSuccess: () => {
      invalidateAll();
      setDeleteTarget(null);
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) =>
      duplicateProject(name, newName),
    onSuccess: () => {
      invalidateAll();
      setDuplicateTarget(null);
      setDuplicateName("");
    },
  });

  const handleExport = async (name: string) => {
    const blob = await exportProject(name);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await importProject(file);
    invalidateAll();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div data-tutorial="projects-header" className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-text-primary tracking-tight">
            Projects
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Manage your literature review projects
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-bg-glass border border-border-glass text-text-secondary hover:text-text-primary hover:border-border-glass-hover transition-colors"
          >
            <Upload size={16} />
            Import
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={handleImport}
          />
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary/15 text-primary border border-primary/20 hover:bg-primary/25 transition-colors"
          >
            <Plus size={16} />
            New Project
          </button>
        </div>
      </div>

      {/* Projects grid */}
      {isLoading ? (
        <div className="text-text-muted text-sm">Loading projects...</div>
      ) : projects.length === 0 ? (
        <GlassCard className="flex flex-col items-center justify-center py-16 text-center">
          <FolderOpen size={48} className="text-text-muted mb-4" />
          <h3 className="text-lg font-semibold text-text-primary mb-2">
            No projects yet
          </h3>
          <p className="text-sm text-text-secondary mb-6 max-w-md">
            Create a new project to start your systematic literature review, or
            import an existing one.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold bg-primary/15 text-primary border border-primary/20 hover:bg-primary/25 transition-colors"
          >
            <Plus size={16} />
            Create Your First Project
          </button>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.name}
              project={project}
              onSwitch={() => switchMutation.mutate(project.name)}
              onDuplicate={() => {
                setDuplicateTarget(project.name);
                setDuplicateName(`${project.display_name} (copy)`);
              }}
              onDelete={() => setDeleteTarget(project.name)}
              onExport={() => handleExport(project.name)}
              isSwitching={switchMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <NameInputModal
          open={showCreateModal}
          onClose={() => {
            setShowCreateModal(false);
            setNewProjectName("");
          }}
          title="Create New Project"
          description="Enter a name for your new literature review project."
          placeholder="e.g., AI in Healthcare Review"
          value={newProjectName}
          onChange={setNewProjectName}
          confirmLabel="Create Project"
          variant="info"
          onConfirm={() => {
            if (newProjectName.trim()) createMutation.mutate(newProjectName.trim());
          }}
        />
      )}

      {/* Duplicate Modal */}
      {duplicateTarget && (
        <NameInputModal
          open={!!duplicateTarget}
          onClose={() => {
            setDuplicateTarget(null);
            setDuplicateName("");
          }}
          title="Duplicate Project"
          description={`Create a copy of "${duplicateTarget}" with a new name.`}
          placeholder="New project name"
          value={duplicateName}
          onChange={setDuplicateName}
          confirmLabel="Duplicate"
          variant="info"
          onConfirm={() => {
            if (duplicateName.trim() && duplicateTarget)
              duplicateMutation.mutate({
                name: duplicateTarget,
                newName: duplicateName.trim(),
              });
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget);
        }}
        variant="danger"
        title="Delete Project?"
        description={`This will permanently delete "${deleteTarget}" and all its data including papers, screening decisions, and exports. This cannot be undone.`}
        confirmLabel="Delete Project"
        cancelLabel="Cancel"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Project Card
// ---------------------------------------------------------------------------

function ProjectCard({
  project,
  onSwitch,
  onDuplicate,
  onDelete,
  onExport,
  isSwitching,
}: {
  project: Project;
  onSwitch: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onExport: () => void;
  isSwitching: boolean;
}) {
  const counts = project.paper_counts;

  return (
    <GlassCard
      className={`flex flex-col gap-4 transition-all ${
        project.is_active ? "border-primary/30 glow-primary" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-text-primary truncate">
              {project.display_name}
            </h3>
            {project.is_active && (
              <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-accent-green/15 text-accent-green border border-accent-green/20">
                Active
              </span>
            )}
          </div>
          <p className="text-xs text-text-muted mt-0.5 font-mono">{project.name}</p>
        </div>
      </div>

      {/* Paper counts */}
      <div className="grid grid-cols-2 gap-2">
        <MiniStat icon={Search} label="Search" value={counts.search} color="text-primary" />
        <MiniStat icon={Database} label="Dedup" value={counts.dedup} color="text-accent-amber" />
        <MiniStat icon={Filter} label="Screened" value={counts.screened} color="text-accent-green" />
        <MiniStat icon={CheckCircle2} label="Eligible" value={counts.eligible} color="text-accent-purple" />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-border-glass">
        {!project.is_active && (
          <button
            onClick={onSwitch}
            disabled={isSwitching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors disabled:opacity-50"
          >
            <ArrowRightLeft size={13} />
            Switch
          </button>
        )}
        <button
          onClick={onDuplicate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-glass text-text-secondary border border-border-glass hover:text-text-primary hover:border-border-glass-hover transition-colors"
        >
          <Copy size={13} />
          Duplicate
        </button>
        <button
          onClick={onExport}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-glass text-text-secondary border border-border-glass hover:text-text-primary hover:border-border-glass-hover transition-colors"
        >
          <Download size={13} />
          Export
        </button>
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent-red/10 text-accent-red border border-accent-red/20 hover:bg-accent-red/20 transition-colors ml-auto"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Mini Stat
// ---------------------------------------------------------------------------

function MiniStat({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Search;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-bg-glass/50">
      <Icon size={13} className={`${color} shrink-0`} />
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs font-semibold text-text-primary ml-auto">
        {value.toLocaleString()}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Name Input Modal (reuses Modal styling but adds an input)
// ---------------------------------------------------------------------------

function NameInputModal({
  open,
  onClose,
  title,
  description,
  placeholder,
  value,
  onChange,
  confirmLabel,
  variant,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  confirmLabel: string;
  variant: "danger" | "info" | "success";
  onConfirm: () => void;
}) {
  if (!open) return null;

  const btnClass =
    variant === "danger"
      ? "bg-accent-red/80 hover:bg-accent-red text-white"
      : variant === "success"
      ? "bg-accent-green/80 hover:bg-accent-green text-bg-base"
      : "bg-primary/80 hover:bg-primary text-bg-base";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative glass-elevated p-0 w-full max-w-md mx-4 shadow-2xl animate-in">
        <div className="p-6 space-y-4">
          <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
          <p className="text-sm text-text-secondary">{description}</p>
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && value.trim()) onConfirm();
            }}
            placeholder={placeholder}
            autoFocus
            className="w-full glass-input px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20"
          />
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-glass">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary bg-bg-glass border border-border-glass hover:bg-bg-elevated hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (value.trim()) onConfirm();
            }}
            disabled={!value.trim()}
            className={`px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50 ${btnClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
      <style jsx>{`
        .animate-in {
          animation: modalIn 0.2s ease-out;
        }
        @keyframes modalIn {
          from { opacity: 0; transform: scale(0.95) translateY(8px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>
    </div>
  );
}
