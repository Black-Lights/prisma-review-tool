"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTutorial } from "@/context/TutorialContext";
import { ChevronRight, ChevronLeft, X, Rocket } from "lucide-react";

type BubblePosition = "right" | "left" | "bottom" | "top";

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const BUBBLE_W = 360;
const BUBBLE_H_EST = 220;
const GAP = 16;
const PAD = 10;

function calcBubblePosition(elRect: Rect): { pos: BubblePosition; x: number; y: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const cx = elRect.left + elRect.width / 2;
  const cy = elRect.top + elRect.height / 2;

  if (elRect.left + elRect.width + GAP + BUBBLE_W + PAD < vw) {
    return { pos: "right", x: elRect.left + elRect.width + GAP, y: Math.max(PAD, Math.min(cy - BUBBLE_H_EST / 2, vh - BUBBLE_H_EST - PAD)) };
  }
  if (elRect.left - GAP - BUBBLE_W > PAD) {
    return { pos: "left", x: elRect.left - GAP - BUBBLE_W, y: Math.max(PAD, Math.min(cy - BUBBLE_H_EST / 2, vh - BUBBLE_H_EST - PAD)) };
  }
  if (elRect.top + elRect.height + GAP + BUBBLE_H_EST + PAD < vh) {
    return { pos: "bottom", x: Math.max(PAD, Math.min(cx - BUBBLE_W / 2, vw - BUBBLE_W - PAD)), y: elRect.top + elRect.height + GAP };
  }
  return { pos: "top", x: Math.max(PAD, Math.min(cx - BUBBLE_W / 2, vw - BUBBLE_W - PAD)), y: Math.max(PAD, elRect.top - GAP - BUBBLE_H_EST) };
}

function Arrow({ pos, elRect, bubbleY }: { pos: BubblePosition; elRect: Rect; bubbleY: number }) {
  const s = 10;

  if (pos === "right") {
    const ay = Math.max(20, Math.min(elRect.top + elRect.height / 2 - bubbleY - s, BUBBLE_H_EST - 40));
    return <div className="absolute" style={{ left: -s, top: ay }}><div style={{ width: 0, height: 0, borderTop: `${s}px solid transparent`, borderBottom: `${s}px solid transparent`, borderRight: `${s}px solid rgba(15,21,36,0.95)` }} /></div>;
  }
  if (pos === "left") {
    const ay = Math.max(20, Math.min(elRect.top + elRect.height / 2 - bubbleY - s, BUBBLE_H_EST - 40));
    return <div className="absolute" style={{ right: -s, top: ay }}><div style={{ width: 0, height: 0, borderTop: `${s}px solid transparent`, borderBottom: `${s}px solid transparent`, borderLeft: `${s}px solid rgba(15,21,36,0.95)` }} /></div>;
  }
  if (pos === "bottom") {
    return <div className="absolute" style={{ top: -s, left: BUBBLE_W / 2 - s }}><div style={{ width: 0, height: 0, borderLeft: `${s}px solid transparent`, borderRight: `${s}px solid transparent`, borderBottom: `${s}px solid rgba(15,21,36,0.95)` }} /></div>;
  }
  return <div className="absolute" style={{ bottom: -s, left: BUBBLE_W / 2 - s }}><div style={{ width: 0, height: 0, borderLeft: `${s}px solid transparent`, borderRight: `${s}px solid transparent`, borderTop: `${s}px solid rgba(15,21,36,0.95)` }} /></div>;
}

/**
 * SVG-based overlay with a rectangular cutout for the highlighted element.
 * This approach works regardless of stacking contexts or overflow containers.
 */
function OverlayWithCutout({ rect, onClick }: { rect: Rect | null; onClick: () => void }) {
  const vw = typeof window !== "undefined" ? window.innerWidth : 1920;
  const vh = typeof window !== "undefined" ? window.innerHeight : 1080;

  return (
    <svg
      className="fixed inset-0 w-full h-full"
      style={{ zIndex: 200, pointerEvents: "auto" }}
      onClick={onClick}
      viewBox={`0 0 ${vw} ${vh}`}
      preserveAspectRatio="none"
    >
      <defs>
        <mask id="tutorial-mask">
          <rect x="0" y="0" width={vw} height={vh} fill="white" />
          {rect && (
            <rect
              x={rect.left - PAD}
              y={rect.top - PAD}
              width={rect.width + PAD * 2}
              height={rect.height + PAD * 2}
              rx="12"
              fill="black"
            />
          )}
        </mask>
      </defs>
      <rect
        x="0" y="0" width={vw} height={vh}
        fill="rgba(0,0,0,0.82)"
        mask="url(#tutorial-mask)"
      />
      {/* Glow border around the cutout */}
      {rect && (
        <rect
          x={rect.left - PAD}
          y={rect.top - PAD}
          width={rect.width + PAD * 2}
          height={rect.height + PAD * 2}
          rx="12"
          fill="none"
          stroke="rgba(125,211,252,0.6)"
          strokeWidth="2.5"
          style={{ filter: "drop-shadow(0 0 12px rgba(125,211,252,0.4)) drop-shadow(0 0 30px rgba(125,211,252,0.15))", pointerEvents: "none" }}
        />
      )}
    </svg>
  );
}

function TutorialOverlay() {
  const { isActive, step, currentStep, totalSteps, next, back, skip } = useTutorial();
  const [elRect, setElRect] = useState<Rect | null>(null);
  const [visible, setVisible] = useState(false);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);

  const updateRect = useCallback(() => {
    if (!step?.target) {
      setElRect(null);
      setVisible(true);
      retryCountRef.current = 0;
      return;
    }
    const el = document.querySelector(step.target) as HTMLElement | null;
    if (el) {
      retryCountRef.current = 0;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => {
        const r = el.getBoundingClientRect();
        setElRect({ top: r.top, left: r.left, width: r.width, height: r.height });
        setVisible(true);
      }, 400);
    } else {
      // Element not found — page may still be loading after navigation
      // Retry up to 15 times (3 seconds total)
      retryCountRef.current++;
      if (retryCountRef.current < 15) {
        setVisible(false);
        retryRef.current = setTimeout(() => updateRect(), 200);
      }
    }
  }, [step]);

  useEffect(() => {
    if (!isActive || !step) { setVisible(false); return; }
    setVisible(false);
    retryCountRef.current = 0;
    const timer = setTimeout(updateRect, 200);
    return () => {
      clearTimeout(timer);
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, [isActive, step, updateRect]);

  // Reposition on resize
  useEffect(() => {
    if (!isActive) return;
    const handle = () => updateRect();
    window.addEventListener("resize", handle);
    return () => window.removeEventListener("resize", handle);
  }, [isActive, updateRect]);

  if (!isActive || !step || !visible) return null;

  const isCenter = !step.target || !elRect;
  const isLast = currentStep === totalSteps - 1;
  const isFirst = currentStep === 0;

  let bubbleX: number, bubbleY: number;
  let bubblePos: BubblePosition = "right";

  if (isCenter) {
    bubbleX = (window.innerWidth - BUBBLE_W) / 2;
    bubbleY = (window.innerHeight - BUBBLE_H_EST) / 2;
  } else {
    const calc = calcBubblePosition(elRect!);
    bubblePos = calc.pos;
    bubbleX = calc.x;
    bubbleY = calc.y;
  }

  return createPortal(
    <>
      {/* SVG overlay with cutout — works across stacking contexts */}
      <OverlayWithCutout rect={isCenter ? null : elRect} onClick={skip} />

      {/* Bubble card */}
      <div
        className="fixed transition-all duration-200 ease-out"
        style={{
          left: bubbleX,
          top: bubbleY,
          width: BUBBLE_W,
          zIndex: 202,
          pointerEvents: "auto",
        }}
      >
        {/* Arrow */}
        {!isCenter && elRect && (
          <Arrow pos={bubblePos} elRect={elRect} bubbleY={bubbleY} />
        )}

        {/* Card */}
        <div
          className="rounded-xl p-5 space-y-3"
          style={{
            background: "rgba(15,21,36,0.95)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(125,211,252,0.2)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5), 0 0 20px rgba(125,211,252,0.08)",
          }}
        >
          {/* Step counter */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-muted">{currentStep + 1} of {totalSteps}</span>
            <button onClick={skip} className="text-text-muted hover:text-text-primary cursor-pointer p-0.5">
              <X size={14} />
            </button>
          </div>

          {/* Title */}
          <h3 className="text-base font-bold text-text-primary">{step.title}</h3>

          {/* Description */}
          <p className="text-sm text-text-secondary leading-relaxed">{step.description}</p>

          {/* Buttons */}
          <div className="flex items-center justify-between pt-1">
            <button onClick={skip} className="text-xs text-text-muted hover:underline cursor-pointer">
              Skip Tutorial
            </button>
            <div className="flex items-center gap-2">
              {!isFirst && (
                <button
                  onClick={back}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-border-glass text-text-secondary hover:text-text-primary hover:border-border-glass-hover transition-colors cursor-pointer"
                >
                  <ChevronLeft size={14} /> Back
                </button>
              )}
              <button
                onClick={next}
                className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-xs font-semibold bg-primary text-bg-base hover:opacity-90 transition-colors cursor-pointer"
              >
                {isLast ? (
                  <><Rocket size={14} /> Start Using App</>
                ) : (
                  <>Next <ChevronRight size={14} /></>
                )}
              </button>
            </div>
          </div>

          {/* Progress dots */}
          <div className="flex justify-center gap-1 pt-1">
            {Array.from({ length: totalSteps }, (_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-colors ${
                  i === currentStep ? "bg-primary" : "bg-border-glass"
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}

export default TutorialOverlay;
