"use client";

import { useState, useCallback, useRef } from "react";
import { askQuestionStream } from "@/lib/api";
import { SourceList } from "@/components/SourceList";
import type { SourceDocument, SourceType } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────────────

interface PanelState {
  answer: string;
  sources: SourceDocument[];
  loading: boolean;
  done: boolean;
  modelUsed: string;
  error: string | null;
}

const EMPTY_PANEL: PanelState = {
  answer: "",
  sources: [],
  loading: false,
  done: false,
  modelUsed: "",
  error: null,
};

// ── Panel config options ────────────────────────────────────────────────────

const PANEL_OPTIONS: { value: SourceType | null; label: string; description: string; color: string }[] = [
  { value: null,             label: "Wszystkie",           description: "Ustawy + orzecznictwo",          color: "text-slate-600 dark:text-slate-300" },
  { value: "legislation",   label: "Ustawy (ISAP)",       description: "Tylko akty prawne",               color: "text-blue-600 dark:text-blue-400" },
  { value: "judgment_nsa",  label: "NSA / WSA",           description: "Sądy administracyjne",            color: "text-purple-600 dark:text-purple-400" },
  { value: "judgment_sn",   label: "Sąd Najwyższy",       description: "Orzeczenia SN",                   color: "text-indigo-600 dark:text-indigo-400" },
  { value: "judgment_tk",   label: "Trybunał Konstytucyjny", description: "Wyroki TK",                    color: "text-red-600 dark:text-red-400" },
  { value: "judgment_common", label: "Sądy powszechne",   description: "Wyroki sądów powszechnych",       color: "text-slate-600 dark:text-slate-300" },
];

// ── Streaming panel ─────────────────────────────────────────────────────────

function ComparePanel({
  panel,
  index,
  sourceType,
  onSourceTypeChange,
  question,
}: {
  panel: PanelState;
  index: number;
  sourceType: SourceType | null;
  onSourceTypeChange: (v: SourceType | null) => void;
  question: string;
}) {
  const opt = PANEL_OPTIONS.find((o) => o.value === sourceType) ?? PANEL_OPTIONS[0];

  return (
    <div className="flex flex-col flex-1 min-w-0 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80">
        <span className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
          Panel {index + 1}
        </span>
        <select
          value={sourceType ?? ""}
          onChange={(e) => onSourceTypeChange((e.target.value || null) as SourceType | null)}
          disabled={panel.loading}
          className="ml-1 flex-1 text-sm bg-transparent border-0 text-slate-700 dark:text-slate-200 font-semibold focus:outline-none cursor-pointer disabled:opacity-50"
        >
          {PANEL_OPTIONS.map((o) => (
            <option key={String(o.value)} value={o.value ?? ""}>
              {o.label} — {o.description}
            </option>
          ))}
        </select>
        {panel.loading && (
          <span className="w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin flex-shrink-0" />
        )}
        {panel.done && !panel.loading && (
          <span className="text-xs text-green-600 dark:text-green-400 font-medium flex-shrink-0">✓</span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Error */}
        {panel.error && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300 text-sm">
            {panel.error}
          </div>
        )}

        {/* Empty state */}
        {!panel.loading && !panel.answer && !panel.error && (
          <div className="flex flex-col items-center justify-center py-16 text-slate-300 dark:text-slate-600">
            <svg className="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <p className="text-sm">Zadaj pytanie aby porównać</p>
          </div>
        )}

        {/* Loading spinner — before sources arrive */}
        {panel.loading && !panel.answer && panel.sources.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <p className="text-sm">Przeszukuję {opt.label}…</p>
          </div>
        )}

        {/* Answer text */}
        {(panel.answer || (panel.loading && panel.sources.length > 0)) && (
          <div>
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-2">
              Odpowiedź
              {panel.modelUsed && (
                <span className="ml-2 font-mono font-normal normal-case">{panel.modelUsed}</span>
              )}
            </p>
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
              {panel.answer}
              {panel.loading && (
                <span className="inline-block w-0.5 h-4 ml-0.5 bg-slate-400 animate-pulse align-middle" />
              )}
            </p>
          </div>
        )}

        {/* Sources */}
        {panel.sources.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-2">
              Źródła ({panel.sources.length})
            </p>
            <SourceList sources={panel.sources} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ComparePage() {
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [sourceTypes, setSourceTypes] = useState<[SourceType | null, SourceType | null]>(
    ["legislation", "judgment_nsa"]
  );
  const [panels, setPanels] = useState<[PanelState, PanelState]>([EMPTY_PANEL, EMPTY_PANEL]);

  const answerRefs = useRef<[string, string]>(["", ""]);

  const updatePanel = useCallback((idx: 0 | 1, patch: Partial<PanelState>) => {
    setPanels((prev) => {
      const next: [PanelState, PanelState] = [{ ...prev[0] }, { ...prev[1] }];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const q = question.trim();
      if (!q) return;

      setSubmitted(q);
      answerRefs.current = ["", ""];
      setPanels([
        { ...EMPTY_PANEL, loading: true },
        { ...EMPTY_PANEL, loading: true },
      ]);

      const runPanel = async (idx: 0 | 1) => {
        const sourceType = sourceTypes[idx];
        try {
          await askQuestionStream(
            q,
            5,
            {
              onSources(sources) {
                updatePanel(idx, { sources });
              },
              onDelta(text) {
                answerRefs.current[idx] += text;
                updatePanel(idx, { answer: answerRefs.current[idx] });
              },
              onDone(modelUsed) {
                updatePanel(idx, { loading: false, done: true, modelUsed });
              },
              onError(detail) {
                updatePanel(idx, { loading: false, error: detail });
              },
            },
            sourceType ? { source_type_filter: sourceType } : undefined
          );
        } catch (err) {
          updatePanel(idx, {
            loading: false,
            error: err instanceof Error ? err.message : "Nieoczekiwany błąd.",
          });
        }
      };

      // Run both panels in parallel
      await Promise.allSettled([runPanel(0), runPanel(1)]);
    },
    [question, sourceTypes, updatePanel]
  );

  const anyLoading = panels[0].loading || panels[1].loading;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="flex-shrink-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <a href="/ask" className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xl font-bold text-blue-600 dark:text-blue-400">⚖️</span>
            <span className="text-lg font-semibold text-slate-900 dark:text-slate-100">LexCorpus</span>
          </a>
          <nav className="flex items-center gap-4 ml-4 text-sm">
            <a href="/ask"     className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Pytaj AI</a>
            <a href="/search"  className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Szukaj</a>
            <a href="/compare" className="text-blue-600 dark:text-blue-400 font-medium border-b-2 border-blue-600 dark:border-blue-400 pb-0.5">Porównaj</a>
            <a href="/history" className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Historia</a>
            <a href="/admin"   className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Admin</a>
          </nav>
        </div>
      </header>

      {/* Question bar */}
      <div className="flex-shrink-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-7xl mx-auto flex gap-3">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Wpisz pytanie prawne — obie kolumny odpowiedzą równolegle…"
            disabled={anyLoading}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!question.trim() || anyLoading}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-medium text-sm transition-colors flex items-center gap-2"
          >
            {anyLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            )}
            Porównaj
          </button>
        </form>

        {submitted && (
          <p className="max-w-7xl mx-auto mt-2 text-xs text-slate-400 dark:text-slate-500 truncate">
            Pytanie: <span className="italic">{submitted}</span>
          </p>
        )}
      </div>

      {/* Two panels */}
      <div className="flex-1 overflow-hidden">
        <div className="max-w-7xl mx-auto h-full px-4 py-4 flex gap-4">
          {([0, 1] as const).map((idx) => (
            <ComparePanel
              key={idx}
              panel={panels[idx]}
              index={idx}
              sourceType={sourceTypes[idx]}
              onSourceTypeChange={(v) =>
                setSourceTypes((prev) => {
                  const next: [SourceType | null, SourceType | null] = [...prev] as [SourceType | null, SourceType | null];
                  next[idx] = v;
                  return next;
                })
              }
              question={submitted}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
