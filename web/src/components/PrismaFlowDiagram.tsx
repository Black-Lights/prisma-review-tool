"use client";

import { useRef, useState } from "react";
import { toPng } from "html-to-image";
import { Download } from "lucide-react";
import type { StatsResponse } from "@/lib/api";

interface Props {
  stats: StatsResponse | undefined;
}

function n(val: number | undefined): string {
  return val !== undefined && val !== null ? val.toLocaleString() : "–";
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* intentionally empty — DownloadActions removed, download button inline */

/* ── Tiny SVG arrow helpers ── */

function ArrowRight() {
  return (
    <svg width="32" height="16" className="shrink-0 mx-0.5" viewBox="0 0 32 16">
      <line x1="0" y1="8" x2="26" y2="8" stroke="#6b7280" strokeWidth="1.5" />
      <polygon points="26,3 32,8 26,13" fill="#6b7280" />
    </svg>
  );
}

function ArrowDown() {
  return (
    <div className="flex justify-center py-0.5">
      <svg width="16" height="20" viewBox="0 0 16 20">
        <line x1="8" y1="0" x2="8" y2="15" stroke="#6b7280" strokeWidth="1.5" />
        <polygon points="3,15 8,20 13,15" fill="#6b7280" />
      </svg>
    </div>
  );
}

export default function PrismaFlowDiagram({ stats }: Props) {
  const diagramRef = useRef<HTMLDivElement>(null);
  const [downloading, setDownloading] = useState(false);

  const handleDownloadPng = async () => {
    if (!diagramRef.current) return;
    setDownloading(true);
    try {
      const dataUrl = await toPng(diagramRef.current, { pixelRatio: 3, backgroundColor: "#ffffff" });
      const link = document.createElement("a");
      link.download = "prisma_2020_flow_diagram.png";
      link.href = dataUrl;
      link.click();
    } finally {
      setDownloading(false);
    }
  };

  const search = stats?.search ?? {};
  const dedup = stats?.dedup ?? {};
  const screen = stats?.screen ?? {};
  const eligibility = stats?.eligibility ?? {};

  const totalIdentified = (search as any).total ?? 0;
  const duplicatesRemoved = (dedup as any).duplicates_removed ?? 0;
  const excluded = (screen as any).excluded ?? 0;
  const maybe = (screen as any).maybe ?? 0;
  const screened = (screen as any).total_screened ?? (dedup as any).remaining ?? 0;
  const screenIncluded = (screen as any).included ?? 0;
  const eligInput = (eligibility as any).input_from_screening ?? screenIncluded;
  const eligIncluded = (eligibility as any).included ?? 0;
  const eligExcluded = (eligibility as any).excluded ?? 0;
  const hasEligibility = eligInput > 0 && ((eligibility as any).screened ?? 0) > 0;
  const finalIncluded = hasEligibility ? eligIncluded : screenIncluded;
  const sourceEntries = Object.entries(search).filter(([k]) => k !== "total");

  /*
   * Layout uses a 3-column CSS grid per row:
   *   [left-box]  [arrow]  [right-box]
   * Down-arrows span the left column only, keeping alignment perfect.
   */
  const grid = "grid gap-0 items-center" as const;
  const cols = { gridTemplateColumns: "1fr 36px 1fr" } as const;
  const box = "border border-gray-700 bg-white p-2.5 text-[11px] text-gray-800 leading-snug";

  return (
    <div className="space-y-3">
      <div ref={diagramRef} className="bg-white rounded-lg overflow-x-auto" style={{ fontFamily: "Arial, Helvetica, sans-serif" }}>
        {/* Title */}
        <div className="text-center text-[11px] text-gray-600 font-medium pt-4 pb-2 px-4">
          PRISMA 2020 flow diagram for new systematic reviews which included searches of databases and registers only
        </div>

        {/* Gold header */}
        <div className="mx-6 mb-3">
          <div className="rounded-full py-1.5 text-center text-[11px] font-bold text-gray-800" style={{ backgroundColor: "#F0AD4E" }}>
            Identification of studies via databases and registers
          </div>
        </div>

        <div className="px-4 pb-4 min-w-[480px]">
          {/* ── IDENTIFICATION ── */}
          <div className="flex gap-1.5">
            <div className="shrink-0 rounded flex items-center justify-center text-white text-[9px] font-bold" style={{ writingMode: "vertical-lr", transform: "rotate(180deg)", width: "22px", backgroundColor: "#5B9BD5", letterSpacing: "0.5px" }}>
              Identification
            </div>
            <div className={`flex-1 ${grid}`} style={cols}>
              <div className={box}>
                <b>Records identified from*:</b><br />
                Databases (n = {n(totalIdentified)})
                {sourceEntries.map(([src, cnt]) => (
                  <div key={src} className="ml-3 text-[10px]">{src}: {n(cnt as number)}</div>
                ))}
              </div>
              <div className="flex justify-center"><ArrowRight /></div>
              <div className={box}>
                <b><i>Records removed before screening:</i></b><br />
                <span className="ml-2">Duplicate records removed (n = {n(duplicatesRemoved)})</span><br />
                <span className="ml-2">Records marked as ineligible by automation tools (n = {n(excluded)})</span><br />
                <span className="ml-2">Records removed for other reasons (n = 0)</span>
              </div>
            </div>
          </div>

          {/* ↓ (under left box only) */}
          <div className="flex gap-1.5">
            <div className="w-[22px] shrink-0" />
            <div className={`flex-1 ${grid}`} style={cols}>
              <ArrowDown />
              <div />
              <div />
            </div>
          </div>

          {/* ── SCREENING ── */}
          <div className="flex gap-1.5">
            <div className="shrink-0 rounded flex items-center justify-center text-white text-[9px] font-bold" style={{ writingMode: "vertical-lr", transform: "rotate(180deg)", width: "22px", backgroundColor: "#5B9BD5", letterSpacing: "0.5px" }}>
              Screening
            </div>
            <div className="flex-1 space-y-0">
              {/* Records screened → excluded */}
              <div className={grid} style={cols}>
                <div className={box}>
                  <b>Records screened</b><br />
                  (n = {n(screened)})
                </div>
                <div className="flex justify-center"><ArrowRight /></div>
                <div className={box}>
                  <b>Records excluded**</b><br />
                  (n = {n(excluded + maybe)})
                </div>
              </div>

              {/* ↓ */}
              <div className={grid} style={cols}>
                <ArrowDown />
                <div />
                <div />
              </div>

              {/* Reports sought → not retrieved */}
              <div className={grid} style={cols}>
                <div className={box}>
                  <b>Reports sought for retrieval</b><br />
                  (n = {n(screenIncluded)})
                </div>
                <div className="flex justify-center"><ArrowRight /></div>
                <div className={box}>
                  <b>Reports not retrieved</b><br />
                  (n = 0)
                </div>
              </div>

              {/* ↓ */}
              <div className={grid} style={cols}>
                <ArrowDown />
                <div />
                <div />
              </div>

              {/* Reports assessed → excluded */}
              <div className={grid} style={cols}>
                <div className={box}>
                  <b>Reports assessed for eligibility</b><br />
                  (n = {n(hasEligibility ? eligInput : screenIncluded)})
                </div>
                <div className="flex justify-center"><ArrowRight /></div>
                <div className={box}>
                  <b>Reports excluded:</b><br />
                  {hasEligibility ? (
                    <span className="ml-2">Stricter criteria (n = {n(eligExcluded)})</span>
                  ) : (
                    <span className="ml-2 italic text-gray-400">Pending eligibility screening</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* ↓ */}
          <div className="flex gap-1.5">
            <div className="w-[22px] shrink-0" />
            <div className={`flex-1 ${grid}`} style={cols}>
              <ArrowDown />
              <div />
              <div />
            </div>
          </div>

          {/* ── INCLUDED ── */}
          <div className="flex gap-1.5">
            <div className="shrink-0 rounded flex items-center justify-center text-white text-[9px] font-bold" style={{ writingMode: "vertical-lr", transform: "rotate(180deg)", width: "22px", backgroundColor: "#5B9BD5", letterSpacing: "0.5px" }}>
              Included
            </div>
            <div className={`flex-1 ${grid}`} style={cols}>
              <div className={box}>
                <b>Studies included in review</b><br />
                (n = {n(finalIncluded)})<br />
                <b>Reports of included studies</b><br />
                (n = {n(finalIncluded)})
              </div>
              <div />
              <div />
            </div>
          </div>
        </div>

        {/* Footnotes */}
        <div className="px-4 pb-3 text-[9px] text-gray-400 leading-relaxed">
          <p>*Consider, if feasible, reporting the number of records identified from each database or register searched (rather than the total number across all databases/registers).</p>
          <p>**If automation tools were used, indicate how many records were excluded by a human and how many were excluded by automation tools.</p>
          <p className="mt-1">Source: Page MJ, et al. BMJ 2021;372:n71. doi: 10.1136/bmj.n71. Licensed under CC BY 4.0.</p>
        </div>
      </div>

      {/* Download */}
      <button
        onClick={handleDownloadPng}
        disabled={downloading}
        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary-dim text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-50 transition-colors cursor-pointer"
      >
        <Download size={16} />
        {downloading ? "Saving..." : "Download PNG"}
      </button>
    </div>
  );
}
