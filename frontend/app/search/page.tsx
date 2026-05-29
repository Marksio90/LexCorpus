"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { searchDocuments } from "@/lib/api";
import { SourceList } from "@/components/SourceList";
import type { SourceDocument, SourceType } from "@/lib/types";

const SOURCE_FILTERS: { value: SourceType | null; label: string }[] = [
  { value: null,                   label: "Wszystkie" },
  { value: "legislation",          label: "Ustawy" },
  { value: "judgment_nsa",         label: "NSA / WSA" },
  { value: "judgment_sn",          label: "Sąd Najwyższy" },
  { value: "judgment_tk",          label: "Trybunał Konstytucyjny" },
  { value: "judgment_common",      label: "Sądy powszechne" },
];

const TOP_K_OPTIONS = [5, 10, 20, 50];

export default function SearchPage() {
  const searchParams = useSearchParams();
  const [query, setQuery]           = useState(searchParams.get("q") ?? "");
  const [sourceType, setSourceType] = useState<SourceType | null>(null);
  const [topK, setTopK]             = useState(10);
  const [results, setResults]       = useState<SourceDocument[] | null>(null);
  const [total, setTotal]           = useState(0);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [lastQuery, setLastQuery]   = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-search if ?q= param present on mount
  useEffect(() => {
    const q = searchParams.get("q");
    if (q?.trim()) handleSearch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await searchDocuments(q, topK, {
        source_type_filter: sourceType,
      });
      setResults(res.results);
      setTotal(res.total);
      setLastQuery(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd wyszukiwania.");
    } finally {
      setLoading(false);
    }
  }, [query, topK, sourceType, loading]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <a href="/ask" className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xl font-bold text-blue-600 dark:text-blue-400">⚖️</span>
            <span className="text-lg font-semibold text-slate-900 dark:text-slate-100">LexCorpus</span>
          </a>
          <nav className="flex items-center gap-4 ml-4 text-sm">
            <a href="/ask"    className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Pytaj AI</a>
            <a href="/search" className="text-blue-600 dark:text-blue-400 font-medium border-b-2 border-blue-600 dark:border-blue-400 pb-0.5">Szukaj</a>
            <a href="/history" className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Historia</a>
            <a href="/admin"  className="text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Admin</a>
          </nav>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Search form */}
        <form onSubmit={handleSearch} className="space-y-4">
          {/* Query input */}
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Szukaj w aktach prawnych i orzecznictwie… (np. przedawnienie zobowiązań podatkowych)"
              disabled={loading}
              className="w-full px-4 py-3 pr-32 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={!query.trim() || loading}
              className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm rounded-lg font-medium transition-colors"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              )}
              Szukaj
            </button>
          </div>

          {/* Filters row */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Source type */}
            <div className="flex flex-wrap gap-1.5">
              {SOURCE_FILTERS.map((f) => (
                <button
                  key={String(f.value)}
                  type="button"
                  onClick={() => setSourceType(f.value)}
                  disabled={loading}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors disabled:opacity-50 ${
                    sourceType === f.value
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-blue-400"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Divider */}
            <span className="text-slate-200 dark:text-slate-700 hidden sm:inline">|</span>

            {/* Top K */}
            <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span>Wyników:</span>
              {TOP_K_OPTIONS.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setTopK(n)}
                  disabled={loading}
                  className={`w-8 h-6 rounded text-xs font-medium transition-colors disabled:opacity-50 ${
                    topK === n
                      ? "bg-slate-700 dark:bg-slate-200 text-white dark:text-slate-900"
                      : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-blue-400"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div className="mt-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="mt-12 flex flex-col items-center gap-3 text-slate-400">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <p className="text-sm">Przeszukuję bazę…</p>
          </div>
        )}

        {/* Results */}
        {results !== null && !loading && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {total > 0 ? (
                  <>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{total}</span>
                    {" "}wyników dla{" "}
                    <span className="font-semibold text-slate-700 dark:text-slate-300">„{lastQuery}"</span>
                  </>
                ) : (
                  <>Brak wyników dla „{lastQuery}"</>
                )}
              </p>
              {total > 0 && (
                <a
                  href={`/ask?q=${encodeURIComponent(lastQuery)}`}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Zapytaj AI o te wyniki →
                </a>
              )}
            </div>

            {total === 0 ? (
              <div className="py-16 text-center text-slate-400 dark:text-slate-500">
                <svg className="w-12 h-12 mx-auto mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm">Spróbuj innych słów kluczowych lub zmień filtr źródeł.</p>
              </div>
            ) : (
              <SourceList sources={results} />
            )}
          </div>
        )}

        {/* Empty state */}
        {results === null && !loading && !error && (
          <div className="mt-16 text-center text-slate-400 dark:text-slate-500">
            <svg className="w-16 h-16 mx-auto mb-4 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            <p className="text-sm font-medium mb-1">Przeszukaj ~636 000 dokumentów</p>
            <p className="text-xs">Akty prawne z ISAP · Wyroki NSA/WSA · Orzeczenia SN · Wyroki TK</p>
          </div>
        )}
      </main>
    </div>
  );
}
