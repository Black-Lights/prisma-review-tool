"use client";

import { useEffect, useRef } from "react";
import { X, AlertTriangle, Info, CheckCircle2 } from "lucide-react";

type ModalVariant = "danger" | "info" | "success";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm?: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ModalVariant;
}

const variantStyles: Record<ModalVariant, { icon: typeof AlertTriangle; iconClass: string; btnClass: string }> = {
  danger: {
    icon: AlertTriangle,
    iconClass: "text-accent-red bg-accent-red/10",
    btnClass: "bg-accent-red/80 hover:bg-accent-red text-white",
  },
  info: {
    icon: Info,
    iconClass: "text-primary bg-primary/10",
    btnClass: "bg-primary/80 hover:bg-primary text-bg-base",
  },
  success: {
    icon: CheckCircle2,
    iconClass: "text-accent-green bg-accent-green/10",
    btnClass: "bg-accent-green/80 hover:bg-accent-green text-bg-base",
  },
};

export default function Modal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "info",
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const style = variantStyles[variant];
  const Icon = style.icon;

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[100] flex items-center justify-center"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Dialog */}
      <div className="relative glass-elevated p-0 w-full max-w-md mx-4 shadow-2xl animate-in">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-bg-glass"
        >
          <X size={18} />
        </button>

        <div className="p-6 space-y-4">
          {/* Icon + Title */}
          <div className="flex items-start gap-4">
            <div className={`shrink-0 p-2.5 rounded-xl ${style.iconClass}`}>
              <Icon size={22} />
            </div>
            <div className="space-y-1.5 pt-0.5">
              <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">{description}</p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-glass">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary bg-bg-glass border border-border-glass hover:bg-bg-elevated hover:text-text-primary"
          >
            {cancelLabel}
          </button>
          {onConfirm && (
            <button
              onClick={() => { onConfirm(); onClose(); }}
              className={`px-4 py-2 rounded-lg text-sm font-semibold ${style.btnClass}`}
            >
              {confirmLabel}
            </button>
          )}
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
