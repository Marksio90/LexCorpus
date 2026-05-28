"use client";

import { useState, useEffect } from "react";
import { getHistory, clearHistory, removeHistoryEntry } from "@/lib/history";
import type { HistoryEntry } from "@/lib/types";
import { SourceList } from "@/components/SourceList";

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setEntries(getHistory());
  }, []);

  function handleClear() {
    if (confirm("Czy na pewno chcesz usunąć całą historię?")) {
      clearHistory();
      setEntries([]);
    }
  }

  function handleDelete(id: string) {
    removeHistoryEntry(id);
    setEntries((prev) => prev.filter((e) => e.id !== id));
    if (expandedId === id) setExpandedId(null);
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleString("pl-PL", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a
              href="/ask"
              className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
            >
              ← Wróć do wyszukiwarki
            </a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <h1 className="text-lg font-semibold">Historia zapytań</h1>
          </div>
          {entries.length > 0 && (
            <button
              onClick={handleClear}
              className="text-sm text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors"
            >
              Wyczyść historię
            </button>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        {!mounted ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-16 text-slate-400 dark:text-slate-500">
            <svg
              className="w-12 h-12 mx-auto mb-4 opacity-50"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <p className="text-lg font-medium">Brak historii</p>
            <p className="text-sm mt-1">Twoje zapytania pojawią się tutaj.</p>
            <a
              href="/ask"
              className="mt-4 inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
            >
              Zadaj pierwsze pytanie
            </a>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {entries.length} {entries.length === 1 ? "zapytanie" : entries.length < 5 ? "zapytania" : "zapytań"}
            </p>
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
              >
                {/* Question row */}
                <div
                  className="flex items-start gap-3 px-4 py-4 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors"
                  onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-800 dark:text-slate-200 truncate">
                      {entry.question}
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                      {formatDate(entry.timestamp)}
                      {" · "}
                      <span className="text-blue-500">{entry.model_used}</span>
                      {entry.sources.length > 0 && (
                        <>
                          {" · "}
                          {entry.sources.length} {entry.sources.length === 1 ? "źródło" : "źródeł"}
                        </>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(entry.id);
                      }}
                      className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                      aria-label="Usuń"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                    <svg
                      className={`w-4 h-4 text-slate-400 transition-transform ${expandedId === entry.id ? "rotate-180" : ""}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>

                {/* Expanded content */}
                {expandedId === entry.id && (
                  <div className="border-t border-slate-100 dark:border-slate-700 px-4 py-4 space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-2">
                        Odpowiedź
                      </h3>
                      <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                        {entry.answer}
                      </p>
                    </div>
                    {entry.sources.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-2">
                          Źródła
                        </h3>
                        <SourceList sources={entry.sources} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
