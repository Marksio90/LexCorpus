"use client";

import { useState } from "react";
import type { SourceDocument, SourceType } from "@/lib/types";

interface SourceListProps {
  sources: SourceDocument[];
}

const SOURCE_TYPE_LABELS: Record<SourceType, { label: string; color: string }> = {
  legislation:        { label: "Ustawa",    color: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300" },
  judgment_nsa:       { label: "NSA/WSA",   color: "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300" },
  judgment_sn:        { label: "SN",        color: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300" },
  judgment_tk:        { label: "TK",        color: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300" },
  judgment_common:    { label: "Sąd",       color: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300" },
  judgment_kio:       { label: "KIO",       color: "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300" },
  unknown:            { label: "Źródło",    color: "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400" },
};

function SourceTypeBadge({ type }: { type: SourceType }) {
  const { label, color } = SOURCE_TYPE_LABELS[type] ?? SOURCE_TYPE_LABELS.unknown;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${color}`}>
      {label}
    </span>
  );
}

function ScoreBadge({ score }: { score: number }) {
  // Cross-encoder scores are raw logits (unbounded). Normalize via sigmoid for display.
  const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
  const normalized = score > 1 || score < 0 ? sigmoid(score) : score;
  const pct = Math.round(normalized * 100);
  const color =
    pct >= 70
      ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
      : pct >= 45
      ? "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300"
      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

function buildIsapUrl(source: SourceDocument): string {
  // Prefer the ELI-based URL from the API (e.g. https://api.sejm.gov.pl/eli/acts/DU/2024/1984/text.html)
  // Convert to the human-readable ISAP page URL when possible.
  if (source.url && source.url.includes("sejm.gov.pl")) {
    // Strip /text.html suffix to get a cleaner link, or use ISAP search
    const eliMatch = source.url.match(/\/eli\/acts\/([A-Z]+)\/(\d+)\/(\d+)/);
    if (eliMatch) {
      const [, pub, year, pos] = eliMatch;
      return `https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WD${pub === "DU" ? "U" : "MP"}${year}${String(pos).padStart(7, "0")}`;
    }
    return source.url;
  }
  if (source.act_id) {
    return `https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=${encodeURIComponent(source.act_id)}`;
  }
  return "";
}

function SourceItem({ source, index }: { source: SourceDocument; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const num = index + 1;
  const isapUrl = buildIsapUrl(source);

  const publisherLabel =
    source.publisher === "WDU"
      ? "Dz.U."
      : source.publisher === "WMP"
      ? "M.P."
      : source.publisher;

  return (
    <div
      id={`source-${num}`}
      className="border border-slate-100 dark:border-slate-700 rounded-lg overflow-hidden scroll-mt-4"
    >
      <div
        className="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Index badge — matches inline [N] citation style */}
        <span className="flex-shrink-0 w-6 h-6 rounded bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-bold flex items-center justify-center mt-0.5">
          {num}
        </span>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SourceTypeBadge type={source.source_type ?? "unknown"} />
            <p className="font-medium text-slate-800 dark:text-slate-200 text-sm leading-snug">
              {source.title || source.act_id}
            </p>
            <ScoreBadge score={source.score} />
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-xs text-slate-400 dark:text-slate-500">
            {source.year && <span>{source.year}</span>}
            {source.publisher && <span>{publisherLabel}</span>}
            {source.pos && <span>poz.&nbsp;{source.pos}</span>}
          </div>
          {source.citation && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 italic truncate">
              {source.citation}
            </p>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {isapUrl && (
            <a
              href={isapUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
            >
              ISAP&nbsp;↗
            </a>
          )}
          <svg
            className={`w-4 h-4 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Expanded text snippet */}
      {expanded && source.text && (
        <div className="border-t border-slate-100 dark:border-slate-700 px-4 py-3 bg-slate-50 dark:bg-slate-800/50">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-2">
            Fragment tekstu
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-wrap">
            {source.text}
          </p>
        </div>
      )}
    </div>
  );
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return <p className="text-sm text-slate-400 dark:text-slate-500">Brak źródeł.</p>;
  }

  return (
    <div className="space-y-2">
      {sources.map((source, index) => (
        <SourceItem key={`${source.act_id}-${source.chunk_index}`} source={source} index={index} />
      ))}
    </div>
  );
}
