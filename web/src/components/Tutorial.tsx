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
const PAD = 8;

function calcBubblePosition(
  elRect: Rect
): { pos: BubblePosition; x: number; y: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const cx = elRect.left + elRect.width / 2;
  const cy = elRect.top + elRect.height / 2;

  // Prefer right
  if (elRect.left + elRect.width + GAP + BUBBLE_W + PAD < vw) {
    return { pos: "right", x: elRect.left + elRect.width + GAP, y: Math.max(PAD, Math.min(cy - BUBBLE_H_EST / 2, vh - BUBBLE_H_EST - PAD)) };
  }
  // Try left
  if (elRect.left - GAP - BUBBLE_W > PAD) {
    return { pos: "left", x: elRect.left - GAP - BUBBLE_W, y: Math.max(PAD, Math.min(cy - BUBBLE_H_EST / 2, vh - BUBBLE_H_EST - PAD)) };
  }
  // Try bottom
  if (elRect.top + elRect.height + GAP + BUBBLE_H_EST + PAD < vh) {
    return { pos: "bottom", x: Math.max(PAD, Math.min(cx - BUBBLE_W / 2, vw - BUBBLE_W - PAD)), y: elRect.top + elRect.height + GAP };
  }
  // Fallback top
  return { pos: "top", x: Math.max(PAD, Math.min(cx - BUBBLE_W / 2, vw - BUBBLE_W - PAD)), y: Math.max(PAD, elRect.top - GAP - BUBBLE_H_EST) };
}

function Arrow({ pos, elRect, bubbleX, bubbleY }: { pos: BubblePosition; elRect: Rect; bubbleX: number; bubbleY: number }) {
  const s = 10;
  const color = "rgba(125,211,252,0.15)";

  if (pos === "right") {
    const ay = elRect.top + elRect.height / 2 - bubbleY;
    return (
      <div className="absolute" style={{ left: -s, top: Math.max(20, Math.min(ay - s, BUBBLE_H_EST - 40)) }}>
        <div style={{ width: 0, height: 0, borderTop: `${s}px solid transparent`, borderBottom: `${s}px solid transparent`, borderRight: `${s}px solid ${color}` }} />
      </div>
    );
  }
  if (pos === "left") {
    const ay = elRect.top + elRect.height / 2 - bubbleY;
    return (
      <div className="absolute" style={{ right: -s, top: Math.max(20, Math.min(ay - s, BUBBLE_H_EST - 40)) }}>
        <div style={{ width: 0, height: 0, borderTop: `${s}px solid transparent`, borderBottom: `${s}px solid transparent`, borderLeft: `${s}px solid ${color}` }} />
      </div>
    );
  }
  if (pos === "bottom") {
    const ax = elRect.left + elRect.width / 2 - bubbleX;
    return (
      <div className="absolute" style={{ top: -s, left: Math.max(20, Math.min(ax - s, BUBBLE_W - 40)) }}>
        <div style={{ width: 0, height: 0, borderLeft: `${s}px solid transparent`, borderRight: `${s}px solid transparent`, borderBottom: `${s}px solid ${color}` }} />
      </div>
    );
  }
  // top
  const ax = elRect.left + elRect.width / 2 - bubbleX;
  return (
    <div className="absolute" style={{ bottom: -s, left: Math.max(20, Math.min(ax - s, BUBBLE_W - 40)) }}>
      <div style={{ width: 0, height: 0, borderLeft: `${s}px solid transparent`, borderRight: `${s}px solid transparent`, borderTop: `${s}px solid ${color}` }} />
    </div>
  );
}

function TutorialOverlay() {
  const { isActive, step, currentStep, totalSteps, next, back, skip } = useTutorial();
  const [elRect, setElRect] = useState<Rect | null>(null);
  const [visible, setVisible] = useState(false);
  const rafRef = useRef<number>(0);

  const updateRect = useCallback(() => {
    if (!step?.target) {
      setElRect(null);
      setVisible(true);
      return;
    }
    const el = document.querySelector(step.target);
    if (el) {
      const r = el.getBoundingClientRect();
      setElRect({ top: r.top, left: r.left, width: r.width, height: r.height });
      setVisible(true);
    } else {
      // Element not yet in DOM (page navigation pending), retry
      setVisible(false);
      rafRef.current = requestAnimationFrame(() => {
        setTimeout(() => updateRect(), 150);
      });
    }
  }, [step]);

  useEffect(() => {
    if (!isActive || !step) { setVisible(false); return; }
    setVisible(false);
    const timer = setTimeout(updateRect, 100);
    return () => { clearTimeout(timer); cancelAnimationFrame(rafRef.current); };
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

  // Bubble position
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
    <div className="fixed inset-0 z-[200]" style={{ pointerEvents: "auto" }}>
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/70 transition-opacity duration-200" onClick={skip} />

      {/* Cutout highlight */}
      {elRect && (
        <div
          className="absolute rounded-lg transition-all duration-200 ease-out"
          style={{
            top: elRect.top - PAD,
            left: elRect.left - PAD,
            width: elRect.width + PAD * 2,
            height: elRect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.7)",
            pointerEvents: "none",
            zIndex: 201,
          }}
        />
      )}

      {/* Bubble card */}
      <div
        className="absolute transition-all duration-200 ease-out"
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
          <Arrow pos={bubblePos} elRect={elRect} bubbleX={bubbleX} bubbleY={bubbleY} />
        )}

        {/* Card */}
        <div
          className="rounded-xl p-5 space-y-3"
          style={{
            background: "rgba(15,21,36,0.95)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(125,211,252,0.15)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
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
            <button
              onClick={skip}
              className="text-xs text-text-muted hover:underline cursor-pointer"
            >
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
                  <>
                    <Rocket size={14} /> Start Using App
                  </>
                ) : (
                  <>
                    Next <ChevronRight size={14} />
                  </>
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
    </div>,
    document.body
  );
}

export default TutorialOverlay;
