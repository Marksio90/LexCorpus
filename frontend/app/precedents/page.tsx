"use client";

import { useState } from "react";

interface SearchHit {
  act_id:      string;
  title:       string;
  source_type: string;
  year:        number | null;
  url:         string | null;
  score:       number;
  text:        string;
  chunk_index: number;
}

const SOURCE_META: Record<string, { label: string; short: string; color: string; dot: string }> = {
  judgment_nsa:    { label: "NSA / WSA",             short: "NSA",  color: "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300",  dot: "bg-purple-500" },
  judgment_sn:     { label: "Sąd Najwyższy",         short: "SN",   color: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300",  dot: "bg-indigo-500" },
  judgment_tk:     { label: "Trybunał Konstytucyjny", short: "TK",  color: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300",              dot: "bg-red-500" },
  judgment_common: { label: "Sąd powszechny",        short: "SP",   color: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300",         dot: "bg-slate-400" },
  judgment_kio:    { label: "KIO",                   short: "KIO",  color: "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300",  dot: "bg-orange-500" },
};

const ALL_TYPES = Object.keys(SOURCE_META);

const TOP_K_OPTIONS = [6, 12, 20];

const EXAMPLE_FACTS = [
  "Pracodawca zwolnił pracownika bez podania przyczyny podczas okresu próbnego. Czy pracownik może odwołać się do sądu pracy?",
  "Najemca nie płaci czynszu od 4 miesięcy i nie reaguje na wezwania. Jakie kroki może podjąć właściciel mieszkania?",
  "Wykonawca robót budowlanych nie dotrzymał terminu i domaga się dodatkowego wynagrodzenia za opóźnienie spowodowane przez zamawiającego.",
];

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-amber-400" : "bg-slate-300 dark:bg-slate-600";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 dark:text-slate-400 tabular-nums">{pct}%</span>
    </div>
  );
}

export default function PrecedentsPage() {
  const [facts,        setFacts]        = useState("");
  const [sourceTypes,  setSourceTypes]  = useState<string[]>(ALL_TYPES);
  const [topK,         setTopK]         = useState(12);
  const [results,      setResults]      = useState<SearchHit[]>([]);
  const [expandedQuery, setExpandedQuery] = useState<string | null>(null);
  const [searching,    setSearching]    = useState(false);
  const [error,        setError]        = useState<string | null>(null);
  const [expanded,     setExpanded]     = useState<Set<string>>(new Set());
  const [done,         setDone]         = useState(false);

  function toggleType(t: string) {
    setSourceTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  async function search() {
    if (!facts.trim() || searching) return;
    setSearching(true);
    setError(null);
    setResults([]);
    setExpandedQuery(null);
    setDone(false);
    setExpanded(new Set());

    try {
      const res  = await fetch("/api/precedents/search", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ facts, sourceTypes, topK }),
      });
      const data = await res.json() as { results: SearchHit[]; expandedQuery?: string; error?: string };
      if (!res.ok) { setError(data.error ?? "Błąd wyszukiwania."); }
      else {
        setResults(data.results);
        setExpandedQuery(data.expandedQuery ?? null);
        setDone(true);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSearching(false);
    }
  }

  function toggleExpand(key: string) {
    setExpanded((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }

  // Group results by source_type
  const grouped = ALL_TYPES.reduce<Record<string, SearchHit[]>>((acc, t) => {
    const hits = results.filter((r) => r.source_type === t);
    if (hits.length) acc[t] = hits;
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Wyszukiwarka precedensów</h1>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Input card */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Opisz stan faktyczny
            </label>
            <textarea
              value={facts}
              onChange={(e) => setFacts(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") void search(); }}
              placeholder="Opisz sytuację prawną własnymi słowami — system znajdzie najistotniejsze orzeczenia…"
              rows={5}
              className="w-full px-4 py-3 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none leading-relaxed"
            />
            <p className="text-xs text-slate-400 mt-1">{facts.length}/3000 znaków · Ctrl+Enter aby wyszukać</p>
          </div>

          {/* Examples */}
          {!facts && (
            <div className="space-y-1.5">
              <p className="text-xs text-slate-400 font-medium">Przykłady:</p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_FACTS.map((ex, i) => (
                  <button
                    key={i}
                    onClick={() => setFacts(ex)}
                    className="text-xs px-3 py-1.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-700 dark:hover:text-blue-300 transition-colors text-left max-w-xs truncate"
                  >
                    {ex.slice(0, 60)}…
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Filters row */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-2 border-t border-slate-100 dark:border-slate-700">
            {/* Court type filter */}
            <div className="flex flex-wrap gap-1.5">
              {ALL_TYPES.map((t) => {
                const m = SOURCE_META[t];
                const active = sourceTypes.includes(t);
                return (
                  <button
                    key={t}
                    onClick={() => toggleType(t)}
                    className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors border ${
                      active
                        ? `${m.color} border-transparent`
                        : "border-slate-200 dark:border-slate-600 text-slate-400 dark:text-slate-500"
                    }`}
                  >
                    {m.short}
                  </button>
                );
              })}
            </div>

            {/* Top K */}
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs text-slate-500 dark:text-slate-400">Wyników:</span>
              {TOP_K_OPTIONS.map((k) => (
                <button
                  key={k}
                  onClick={() => setTopK(k)}
                  className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors ${
                    topK === k
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={search}
            disabled={searching || !facts.trim() || sourceTypes.length === 0}
            className="w-full py-3 bg-blue-600 text-white rounded-xl font-semibold text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {searching ? (
              <>
                <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                Wyszukiwanie i analiza AI…
              </>
            ) : (
              "⚖️ Znajdź precedensy"
            )}
          </button>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Expanded query */}
        {expandedQuery && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3 text-xs text-amber-700 dark:text-amber-300">
            <span className="font-semibold">Zapytanie AI: </span>{expandedQuery}
          </div>
        )}

        {/* Results */}
        {done && results.length === 0 && (
          <div className="text-center py-10 text-slate-400 text-sm">
            <p className="text-2xl mb-2">🔍</p>
            <p>Nie znaleziono orzeczeń pasujących do opisu. Spróbuj rozszerzyć opis lub zmienić filtry.</p>
          </div>
        )}

        {Object.entries(grouped).map(([type, hits]) => {
          const m = SOURCE_META[type];
          return (
            <div key={type} className="space-y-3">
              {/* Group header */}
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${m.dot}`} />
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{m.label}</h2>
                <span className="text-xs text-slate-400">({hits.length})</span>
              </div>

              {hits.map((hit) => {
                const key      = `${hit.act_id}__${hit.chunk_index}`;
                const isExpand = expanded.has(key);
                const askUrl   = `/ask?q=${encodeURIComponent(`Omów orzeczenie: ${hit.title}${hit.year ? ` (${hit.year})` : ""}. ${hit.text.slice(0, 200)}`)}`;

                return (
                  <div
                    key={key}
                    className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5 space-y-3"
                  >
                    {/* Title row */}
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${m.color}`}>
                            {m.short}
                          </span>
                          {hit.year && (
                            <span className="text-xs text-slate-400">{hit.year}</span>
                          )}
                        </div>
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 leading-snug">
                          {hit.title}
                        </p>
                      </div>
                      <ScoreBar score={hit.score} />
                    </div>

                    {/* Text excerpt */}
                    <p className={`text-sm text-slate-600 dark:text-slate-400 leading-relaxed ${isExpand ? "" : "line-clamp-3"}`}>
                      {hit.text}
                    </p>

                    {/* Actions */}
                    <div className="flex items-center gap-3 flex-wrap pt-1 border-t border-slate-100 dark:border-slate-700">
                      <button
                        onClick={() => toggleExpand(key)}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        {isExpand ? "Zwiń ↑" : "Rozwiń ↓"}
                      </button>
                      <a
                        href={askUrl}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Zapytaj AI o ten wyrok →
                      </a>
                      {hit.url && (
                        <a
                          href={hit.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-slate-500 dark:text-slate-400 hover:underline ml-auto"
                        >
                          Źródło ↗
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </main>
    </div>
  );
}
