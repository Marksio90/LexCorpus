"use client";

import { useState } from "react";
import type { SourceDocument } from "@/lib/types";

interface SourceListProps {
  sources: SourceDocument[];
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 80
      ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
      : pct >= 60
      ? "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300"
      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

function SourceItem({ source, index }: { source: SourceDocument; index: number }) {
  const [expanded, setExpanded] = useState(false);

  const isapUrl = source.act_id
    ? `https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=${encodeURIComponent(source.act_id)}`
    : source.url;

  const publisherLabel =
    source.publisher === "WDU"
      ? "Dziennik Ustaw"
      : source.publisher === "WMP"
      ? "Monitor Polski"
      : source.publisher;

  return (
    <div className="border border-slate-100 dark:border-slate-700 rounded-lg overflow-hidden">
      <div
        className="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Index */}
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center mt-0.5">
          {index + 1}
        </span>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-slate-800 dark:text-slate-200 text-sm leading-snug">
              {source.title}
            </p>
            <ScoreBadge score={source.score} />
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-xs text-slate-400 dark:text-slate-500">
            <span>{source.year}</span>
            <span>{publisherLabel}</span>
            {source.pos && <span>poz. {source.pos}</span>}
            {source.citation && (
              <span className="italic text-slate-500 dark:text-slate-400">{source.citation}</span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <a
            href={isapUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
          >
            ISAP ↗
          </a>
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
          <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed font-mono whitespace-pre-wrap">
            {source.text}
          </p>
        </div>
      )}
    </div>
  );
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return (
      <p className="text-sm text-slate-400 dark:text-slate-500">Brak źródeł.</p>
    );
  }

  return (
    <div className="space-y-2">
      {sources.map((source, index) => (
        <SourceItem key={`${source.act_id}-${source.chunk_index}`} source={source} index={index} />
      ))}
    </div>
  );
}
