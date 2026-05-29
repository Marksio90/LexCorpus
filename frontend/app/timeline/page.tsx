"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

interface ActSummary {
  actId:       string;
  title:       string;
  sourceType:  string;
  year:        number | null;
  url:         string | null;
  detectedAt:  string;
  changeCount: number;
}

const SOURCE_LABELS: Record<string, string> = {
  legislation:     "Ustawa",
  judgment_nsa:    "NSA/WSA",
  judgment_sn:     "SN",
  judgment_tk:     "TK",
  judgment_common: "Sąd powszechny",
  judgment_kio:    "KIO",
};

export default function TimelinePage() {
  const router = useRouter();
  const [query,   setQuery]   = useState("");
  const [acts,    setActs]    = useState<ActSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadActs = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      const res  = await fetch(`/api/timeline/acts${q ? `?q=${encodeURIComponent(q)}` : ""}`);
      const data = await res.json() as ActSummary[];
      setActs(data);
      setLoading(false);
    }, q ? 350 : 0);
  }, []);

  useEffect(() => { loadActs(""); }, [loadActs]);
  useEffect(() => { if (query !== "") loadActs(query); }, [query, loadActs]);

  function openTimeline(actId: string) {
    router.push(`/timeline/${encodeURIComponent(actId)}`);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Historia zmian aktów</h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl px-5 py-4 text-sm text-blue-700 dark:text-blue-300">
          Poniżej akty prawne i orzeczenia, w których system wykrył zmiany podczas synchronizacji z ISAP/SAOS.
          Kliknij akt, aby zobaczyć pełną chronologię zmian.
        </div>

        {/* Search */}
        <div className="relative">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Szukaj aktu prawnego…"
            className="w-full pl-10 pr-4 py-3 text-sm border border-slate-200 dark:border-slate-600 rounded-2xl bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
          />
          <svg className="absolute left-3.5 top-3.5 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {/* Acts list */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : acts.length === 0 ? (
          <div className="text-center py-12 text-slate-400">
            <p className="text-3xl mb-2">📜</p>
            <p className="text-sm">{query ? "Nie znaleziono aktów pasujących do zapytania." : "Brak zarejestrowanych zmian. Uruchom sync aby wypełnić bazę."}</p>
          </div>
        ) : (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <ul className="divide-y divide-slate-100 dark:divide-slate-700">
              {acts.map((act) => (
                <li
                  key={act.actId}
                  onClick={() => openTimeline(act.actId)}
                  className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors group"
                >
                  {/* Change count badge */}
                  <div className="shrink-0 w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/30 flex flex-col items-center justify-center">
                    <span className="text-sm font-bold text-blue-700 dark:text-blue-300 leading-none">{act.changeCount}</span>
                    <span className="text-[9px] text-blue-500 dark:text-blue-400 leading-none mt-0.5">zmian</span>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                        {act.title}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <span className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 px-1.5 py-0.5 rounded-md font-mono text-[10px]">
                        {act.actId}
                      </span>
                      {SOURCE_LABELS[act.sourceType] && (
                        <span className="bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded-md">
                          {SOURCE_LABELS[act.sourceType]}
                        </span>
                      )}
                      {act.year && <span>{act.year}</span>}
                      <span>·</span>
                      <span>ostatnia zmiana {new Date(act.detectedAt).toLocaleDateString("pl-PL")}</span>
                    </div>
                  </div>

                  <svg className="w-4 h-4 text-slate-300 group-hover:text-blue-400 transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
