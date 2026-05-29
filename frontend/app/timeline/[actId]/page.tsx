"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";

interface LegalChange {
  id:         string;
  detectedAt: string;
  actId:      string;
  title:      string;
  sourceType: string;
  year:       number | null;
  summary:    string;
  chunkText:  string;
  url:        string | null;
}

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  legislation:     { label: "Ustawa / Rozporządzenie", color: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300" },
  judgment_nsa:    { label: "Wyrok NSA/WSA",           color: "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300" },
  judgment_sn:     { label: "Wyrok SN",                color: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300" },
  judgment_tk:     { label: "Wyrok TK",                color: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300" },
  judgment_common: { label: "Sąd powszechny",          color: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300" },
  judgment_kio:    { label: "Wyrok KIO",               color: "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300" },
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("pl-PL", {
    day: "2-digit", month: "long", year: "numeric",
  });
}

export default function ActTimelinePage({
  params,
}: {
  params: Promise<{ actId: string }>;
}) {
  const { actId } = use(params);
  const decodedId = decodeURIComponent(actId);
  const router    = useRouter();

  const [changes,    setChanges]    = useState<LegalChange[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [expanded,   setExpanded]   = useState<Set<string>>(new Set());
  const [diffPair,   setDiffPair]   = useState<[string, string] | null>(null);

  async function loadPage(cursor?: string) {
    const url = `/api/timeline/${encodeURIComponent(decodedId)}${cursor ? `?cursor=${cursor}` : ""}`;
    const res  = await fetch(url);
    const data = await res.json() as { items: LegalChange[]; nextCursor: string | null };
    return data;
  }

  useEffect(() => {
    loadPage().then(({ items, nextCursor: nc }) => {
      setChanges(items);
      setNextCursor(nc);
      setLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decodedId]);

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    const { items, nextCursor: nc } = await loadPage(nextCursor);
    setChanges((prev) => [...prev, ...items]);
    setNextCursor(nc);
    setLoadingMore(false);
  }

  function toggleExpand(id: string) {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  function toggleDiff(id: string) {
    setDiffPair((p) => {
      if (!p) return [id, ""];
      const [a, b] = p;
      if (a === id) return null;
      if (b === "") return [a, id];
      return [id, ""];
    });
  }

  const diffA = diffPair ? changes.find((c) => c.id === diffPair[0]) : null;
  const diffB = diffPair ? changes.find((c) => c.id === diffPair[1]) : null;

  const title = changes[0]?.title ?? decodedId;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-start gap-3">
          <button
            onClick={() => router.back()}
            className="text-blue-600 dark:text-blue-400 hover:underline text-sm shrink-0 mt-0.5"
          >
            ← Wróć
          </button>
          <span className="text-slate-300 dark:text-slate-600 mt-0.5">|</span>
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100 leading-tight">{title}</h1>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{decodedId}</p>
          </div>
          {changes[0]?.url && (
            <a
              href={changes[0].url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-0.5"
            >
              ISAP ↗
            </a>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Diff panel */}
        {diffPair && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-slate-700">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm">
                Porównanie wersji
              </h2>
              <button
                onClick={() => setDiffPair(null)}
                className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                ✕ Zamknij
              </button>
            </div>
            {diffPair[1] === "" ? (
              <p className="px-5 py-4 text-sm text-slate-500 dark:text-slate-400">
                Kliknij „Porównaj" przy drugiej wersji, aby zobaczyć różnice.
              </p>
            ) : (
              <div className="grid grid-cols-2 divide-x divide-slate-100 dark:divide-slate-700">
                <DiffPanel change={diffA} label="Wersja A" />
                <DiffPanel change={diffB} label="Wersja B" />
              </div>
            )}
          </div>
        )}

        {/* Timeline */}
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : changes.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-sm">
            <p className="text-2xl mb-2">📋</p>
            <p>Brak zarejestrowanych zmian dla tego aktu.</p>
          </div>
        ) : (
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-5 top-0 bottom-0 w-0.5 bg-slate-200 dark:bg-slate-700" />

            <ul className="space-y-0">
              {changes.map((change, idx) => {
                const isExpanded = expanded.has(change.id);
                const src = SOURCE_LABELS[change.sourceType] ?? { label: change.sourceType, color: "bg-slate-100 text-slate-600" };
                const isDiffA = diffPair?.[0] === change.id;
                const isDiffB = diffPair?.[1] === change.id;

                return (
                  <li key={change.id} className="relative pl-14 pb-8 last:pb-0">
                    {/* Timeline dot */}
                    <div className={`absolute left-3.5 top-1.5 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 ${
                      idx === 0
                        ? "bg-blue-600 scale-125"
                        : "bg-slate-300 dark:bg-slate-600"
                    }`} />

                    {/* Card */}
                    <div className={`bg-white dark:bg-slate-800 rounded-2xl border transition-all ${
                      isDiffA || isDiffB
                        ? "border-blue-400 dark:border-blue-500 shadow-sm shadow-blue-100 dark:shadow-blue-900/30"
                        : "border-slate-200 dark:border-slate-700"
                    }`}>
                      <div className="px-5 py-4">
                        {/* Date + badges */}
                        <div className="flex items-start gap-2 mb-2 flex-wrap">
                          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0 mt-0.5">
                            {formatDate(change.detectedAt)}
                          </span>
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${src.color}`}>
                            {src.label}
                          </span>
                          {idx === 0 && (
                            <span className="text-[11px] px-2 py-0.5 rounded-full font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                              Najnowsza
                            </span>
                          )}
                        </div>

                        {/* Summary */}
                        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
                          {change.summary}
                        </p>

                        {/* Actions */}
                        <div className="flex items-center gap-3 flex-wrap">
                          <button
                            onClick={() => toggleExpand(change.id)}
                            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            {isExpanded ? "Ukryj fragment ↑" : "Pokaż fragment tekstu ↓"}
                          </button>
                          <button
                            onClick={() => toggleDiff(change.id)}
                            className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${
                              isDiffA || isDiffB
                                ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                                : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
                            }`}
                          >
                            {isDiffA ? "Wersja A ✓" : isDiffB ? "Wersja B ✓" : "Porównaj"}
                          </button>
                          {change.url && (
                            <a
                              href={change.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-slate-500 dark:text-slate-400 hover:underline"
                            >
                              Źródło ↗
                            </a>
                          )}
                        </div>

                        {/* Expanded chunk text */}
                        {isExpanded && (
                          <div className="mt-3 bg-slate-50 dark:bg-slate-700/50 rounded-xl p-4 border border-slate-100 dark:border-slate-600">
                            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wide">
                              Fragment przepisu
                            </p>
                            <p className="text-xs text-slate-600 dark:text-slate-300 font-mono leading-relaxed whitespace-pre-wrap">
                              {change.chunkText}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>

            {nextCursor && (
              <div className="pl-14 pt-4">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                >
                  {loadingMore ? "Ładowanie…" : "Załaduj starsze zmiany ↓"}
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function DiffPanel({ change, label }: { change: LegalChange | null | undefined; label: string }) {
  if (!change) {
    return (
      <div className="px-5 py-4 text-sm text-slate-400 italic">
        Wybierz wersję z osi czasu
      </div>
    );
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "2-digit", month: "long", year: "numeric",
    });
  }

  return (
    <div className="px-5 py-4 space-y-2">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-xs text-slate-400">{formatDate(change.detectedAt)}</p>
      <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed border-b border-slate-100 dark:border-slate-700 pb-3">
        {change.summary}
      </p>
      <p className="text-xs font-mono text-slate-600 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
        {change.chunkText}
      </p>
    </div>
  );
}
