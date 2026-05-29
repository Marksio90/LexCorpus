"use client";

import { useState, useEffect, useMemo } from "react";
import { getHistory, clearHistory, removeHistoryEntry } from "@/lib/history";
import type { HistoryEntry } from "@/lib/types";
import { SourceList } from "@/components/SourceList";

type DateFilter = "all" | "today" | "week" | "month";

const DATE_FILTER_LABELS: Record<DateFilter, string> = {
  all:   "Wszystkie",
  today: "Dziś",
  week:  "Ten tydzień",
  month: "Ten miesiąc",
};

function passesDateFilter(entry: HistoryEntry, filter: DateFilter): boolean {
  if (filter === "all") return true;
  const now = new Date();
  const ts  = new Date(entry.timestamp);
  if (filter === "today") {
    return ts.toDateString() === now.toDateString();
  }
  if (filter === "week") {
    const msWeek = 7 * 24 * 60 * 60 * 1000;
    return now.getTime() - ts.getTime() <= msWeek;
  }
  if (filter === "month") {
    return ts.getMonth() === now.getMonth() && ts.getFullYear() === now.getFullYear();
  }
  return true;
}

function highlight(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const re = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  const parts = text.split(re);
  return parts.map((part, i) =>
    re.test(part)
      ? <mark key={i} className="bg-yellow-200 dark:bg-yellow-800/60 text-inherit rounded px-0.5">{part}</mark>
      : part
  );
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("pl-PL", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function pluralPL(n: number, one: string, few: string, many: string) {
  if (n === 1) return one;
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return few;
  return many;
}

export default function HistoryPage() {
  const [allEntries, setAllEntries] = useState<HistoryEntry[]>([]);
  const [mounted,    setMounted]    = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [search,     setSearch]     = useState("");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");

  useEffect(() => {
    getHistory().then((entries) => {
      setAllEntries(entries);
      setMounted(true);
    });
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allEntries.filter((e) => {
      if (!passesDateFilter(e, dateFilter)) return false;
      if (!q) return true;
      return (
        e.question.toLowerCase().includes(q) ||
        e.answer.toLowerCase().includes(q)
      );
    });
  }, [allEntries, search, dateFilter]);

  function handleClear() {
    if (confirm("Czy na pewno chcesz usunąć całą historię?")) {
      void clearHistory();
      setAllEntries([]);
      setExpandedId(null);
    }
  }

  function handleDelete(id: string) {
    void removeHistoryEntry(id);
    setAllEntries((prev) => prev.filter((e) => e.id !== id));
    if (expandedId === id) setExpandedId(null);
  }

  const total   = allEntries.length;
  const showing = filtered.length;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">
              ← Wróć
            </a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Historia zapytań
            </h1>
          </div>
          {total > 0 && (
            <button
              onClick={handleClear}
              className="text-sm text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors"
            >
              Wyczyść wszystko
            </button>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-4">
        {/* Search + filter bar */}
        {mounted && total > 0 && (
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Search input */}
            <div className="relative flex-1">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Szukaj w pytaniach i odpowiedziach…"
                className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            {/* Date filter pills */}
            <div className="flex gap-1.5 flex-wrap">
              {(Object.keys(DATE_FILTER_LABELS) as DateFilter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setDateFilter(f)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    dateFilter === f
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-blue-400"
                  }`}
                >
                  {DATE_FILTER_LABELS[f]}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading */}
        {!mounted && (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        )}

        {/* Empty state — no history at all */}
        {mounted && total === 0 && (
          <div className="text-center py-16 text-slate-400 dark:text-slate-500">
            <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-lg font-medium">Brak historii</p>
            <p className="text-sm mt-1">Twoje zapytania pojawią się tutaj.</p>
            <a href="/ask" className="mt-4 inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm">
              Zadaj pierwsze pytanie
            </a>
          </div>
        )}

        {/* No results for current filter */}
        {mounted && total > 0 && showing === 0 && (
          <div className="text-center py-12 text-slate-400 dark:text-slate-500">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="text-sm font-medium">Brak wyników</p>
            <p className="text-xs mt-1">Spróbuj innych słów lub zmień zakres dat.</p>
            <button onClick={() => { setSearch(""); setDateFilter("all"); }} className="mt-3 text-xs text-blue-600 dark:text-blue-400 hover:underline">
              Wyczyść filtry
            </button>
          </div>
        )}

        {/* Results */}
        {mounted && showing > 0 && (
          <>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {showing < total
                ? `${showing} z ${total} ${pluralPL(total, "zapytania", "zapytań", "zapytań")}`
                : `${total} ${pluralPL(total, "zapytanie", "zapytania", "zapytań")}`}
            </p>

            <div className="space-y-2">
              {filtered.map((entry) => (
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
                      <p className="font-medium text-slate-800 dark:text-slate-200 leading-snug">
                        {highlight(entry.question, search)}
                      </p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                        {formatDate(entry.timestamp)}
                        {" · "}
                        <span className="text-blue-500 dark:text-blue-400">{entry.model_used}</span>
                        {entry.sources.length > 0 && (
                          <> · {entry.sources.length} {pluralPL(entry.sources.length, "źródło", "źródła", "źródeł")}</>
                        )}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0 mt-0.5">
                      <a
                        href={`/ask?q=${encodeURIComponent(entry.question)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="hidden sm:inline text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
                        title="Zadaj ponownie"
                      >
                        Zadaj ponownie
                      </a>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(entry.id); }}
                        className="p-1 text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors"
                        aria-label="Usuń"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                      <svg
                        className={`w-4 h-4 text-slate-400 transition-transform ${expandedId === entry.id ? "rotate-180" : ""}`}
                        fill="none" stroke="currentColor" viewBox="0 0 24 24"
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
                          {highlight(entry.answer, search)}
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
                      <div className="flex justify-end">
                        <a
                          href={`/ask?q=${encodeURIComponent(entry.question)}`}
                          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          Zadaj pytanie ponownie →
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
