"use client";

import { useState, useEffect } from "react";

interface LegalChange {
  id:         string;
  title:      string;
  sourceType: string;
  year:       number | null;
  summary:    string;
  url:        string | null;
  detectedAt: string;
}

interface Alert {
  id:         string;
  read:       boolean;
  createdAt:  string;
  similarity: number;
  question:   string;
  change:     LegalChange;
}

const SOURCE_LABELS: Record<string, string> = {
  legislation:     "Ustawa",
  judgment_nsa:    "NSA/WSA",
  judgment_sn:     "SN",
  judgment_tk:     "TK",
  judgment_common: "Sąd powszechny",
  judgment_kio:    "KIO",
};
const SOURCE_COLORS: Record<string, string> = {
  legislation:     "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300",
  judgment_nsa:    "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300",
  judgment_sn:     "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300",
  judgment_tk:     "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300",
  judgment_common: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300",
  judgment_kio:    "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("pl-PL", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function SimilarityBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "text-red-600 dark:text-red-400"
              : pct >= 80 ? "text-orange-600 dark:text-orange-400"
              : "text-yellow-600 dark:text-yellow-400";
  return (
    <span className={`text-xs font-semibold ${color}`} title="Dopasowanie do Twojego pytania">
      {pct}% dopasowania
    </span>
  );
}

export default function AlertsPage() {
  const [alerts,  setAlerts]  = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState<"all" | "unread">("unread");

  useEffect(() => {
    fetch("/api/alerts")
      .then((r) => r.ok ? r.json() : [])
      .then((d) => { setAlerts(d); setLoading(false); });
  }, []);

  async function markRead(id: string) {
    await fetch(`/api/alerts/${id}/read`, { method: "POST" });
    setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, read: true } : a));
  }

  async function markAllRead() {
    const unread = alerts.filter((a) => !a.read);
    await Promise.all(unread.map((a) => fetch(`/api/alerts/${a.id}/read`, { method: "POST" })));
    setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
  }

  const shown   = filter === "unread" ? alerts.filter((a) => !a.read) : alerts;
  const unreadN = alerts.filter((a) => !a.read).length;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              Zmiany w prawie
              {unreadN > 0 && (
                <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                  {unreadN}
                </span>
              )}
            </h1>
          </div>
          {unreadN > 0 && (
            <button
              onClick={markAllRead}
              className="text-sm text-slate-500 dark:text-slate-400 hover:text-blue-600 transition-colors"
            >
              Oznacz wszystkie jako przeczytane
            </button>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-4">

        {/* Filter pills */}
        <div className="flex gap-2">
          {(["unread", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                filter === f
                  ? "bg-blue-600 border-blue-600 text-white"
                  : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-blue-400"
              }`}
            >
              {f === "unread" ? `Nieprzeczytane (${unreadN})` : `Wszystkie (${alerts.length})`}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        )}

        {/* Empty */}
        {!loading && shown.length === 0 && (
          <div className="text-center py-16 text-slate-400 dark:text-slate-500">
            <svg className="w-12 h-12 mx-auto mb-4 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <p className="font-medium">
              {filter === "unread" ? "Wszystko przeczytane" : "Brak alertów"}
            </p>
            <p className="text-sm mt-1">
              Alerty pojawią się gdy zmienią się przepisy związane z Twoimi pytaniami.
            </p>
          </div>
        )}

        {/* Alert cards */}
        {!loading && shown.map((alert) => (
          <div
            key={alert.id}
            className={`bg-white dark:bg-slate-800 rounded-2xl border overflow-hidden transition-all ${
              alert.read
                ? "border-slate-200 dark:border-slate-700 opacity-70"
                : "border-blue-200 dark:border-blue-800 shadow-sm shadow-blue-100 dark:shadow-blue-900/20"
            }`}
          >
            {/* Top bar */}
            <div className={`h-1 ${alert.read ? "bg-slate-200 dark:bg-slate-700" : "bg-gradient-to-r from-blue-500 to-indigo-500"}`} />

            <div className="px-5 py-4">
              {/* Header row */}
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SOURCE_COLORS[alert.change.sourceType] ?? SOURCE_COLORS.judgment_common}`}>
                    {SOURCE_LABELS[alert.change.sourceType] ?? alert.change.sourceType}
                  </span>
                  {alert.change.year && (
                    <span className="text-xs text-slate-400">{alert.change.year}</span>
                  )}
                  <SimilarityBadge value={alert.similarity} />
                  {!alert.read && (
                    <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
                  )}
                </div>
                <span className="text-xs text-slate-400 shrink-0">{formatDate(alert.change.detectedAt)}</span>
              </div>

              {/* Title */}
              <p className="font-semibold text-slate-900 dark:text-slate-100 text-sm leading-snug mb-2">
                {alert.change.title}
              </p>

              {/* Summary */}
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-3 leading-relaxed">
                {alert.change.summary}
              </p>

              {/* Related question */}
              <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg px-3 py-2 mb-3 text-xs text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-700 dark:text-slate-300">Twoje pytanie: </span>
                &ldquo;{alert.question}&rdquo;
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3">
                {alert.change.url && (
                  <a
                    href={alert.change.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    Otwórz dokument ↗
                  </a>
                )}
                <a
                  href={`/ask?q=${encodeURIComponent(alert.question)}`}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Zapytaj ponownie →
                </a>
                {!alert.read && (
                  <button
                    onClick={() => markRead(alert.id)}
                    className="ml-auto text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  >
                    Oznacz jako przeczytane
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Info box */}
        {!loading && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl border border-blue-100 dark:border-blue-800 px-5 py-4 text-sm text-blue-700 dark:text-blue-300">
            <p className="font-medium mb-1">Jak działają alerty?</p>
            <p className="text-xs text-blue-600 dark:text-blue-400">
              Co tydzień system synchronizuje nowe orzeczenia i przepisy. Gdy nowy dokument
              jest semantycznie podobny do Twoich pytań (podobieństwo &gt; 72%), dostajesz alert.
              Im wyższy procent dopasowania, tym bardziej zmiana dotyczy Twojej sprawy.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
