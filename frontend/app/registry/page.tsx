"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSession } from "next-auth/react";

interface SearchResult {
  act_id:      string;
  title:       string;
  source_type: string;
  year:        number | null;
  url:         string | null;
  score:       number;
}

interface Subscription {
  id:        string;
  actId:     string;
  title:     string;
  url:       string | null;
  createdAt: string;
}

const TIER_LIMITS: Record<string, number> = { free: 5, pro: 50, kancelaria: 9999 };

export default function RegistryPage() {
  const { data: session } = useSession();
  const tier  = session?.user?.tier ?? "free";
  const limit = TIER_LIMITS[tier] ?? 5;

  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const [subs,     setSubs]     = useState<Subscription[]>([]);
  const [subsLoaded, setSubsLoaded] = useState(false);
  const [adding,   setAdding]   = useState<string | null>(null);   // actId being added
  const [error,    setError]    = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load subscriptions
  useEffect(() => {
    fetch("/api/registry/subscriptions")
      .then((r) => r.json())
      .then((d: Subscription[]) => { setSubs(d); setSubsLoaded(true); })
      .catch(() => setSubsLoaded(true));
  }, []);

  // Debounced search
  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.length < 2) { setResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await fetch(`/api/registry/search?q=${encodeURIComponent(q)}`);
        const d   = await res.json() as SearchResult[];
        setResults(d);
      } finally {
        setSearching(false);
      }
    }, 350);
  }, []);

  useEffect(() => { search(query); }, [query, search]);

  async function subscribe(r: SearchResult) {
    setError(null);
    setAdding(r.act_id);
    const res = await fetch("/api/registry/subscriptions", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ actId: r.act_id, title: r.title, url: r.url }),
    });
    const data = await res.json() as Subscription & { error?: string };
    if (!res.ok) {
      setError(data.error ?? "Błąd subskrypcji.");
    } else {
      setSubs((prev) => [data, ...prev]);
    }
    setAdding(null);
  }

  async function unsubscribe(id: string) {
    await fetch(`/api/registry/subscriptions/${id}`, { method: "DELETE" });
    setSubs((prev) => prev.filter((s) => s.id !== id));
  }

  const subscribedIds = new Set(subs.map((s) => s.actId));

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Monitoring rejestru</h1>
          <span className="ml-auto text-xs text-slate-400">
            {subsLoaded ? `${subs.length} / ${limit === 9999 ? "∞" : limit} subskrypcji` : ""}
          </span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Info banner */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl px-5 py-4 text-sm text-blue-700 dark:text-blue-300">
          <strong>Jak działa monitoring?</strong> Subskrybujesz konkretne akty prawne.
          Gdy system wykryje zmianę (po cotygodniowej synchronizacji z ISAP/SAOS),
          dostaniesz natychmiastowy e-mail — bez czekania na newsletter.
        </div>

        {/* Search */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
          <h2 className="font-semibold text-slate-800 dark:text-slate-200">Szukaj aktów prawnych</h2>
          <div className="relative">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="np. Kodeks pracy, ustawa o VAT, Prawo zamówień publicznych…"
              className="w-full pl-10 pr-4 py-2.5 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <svg className="absolute left-3 top-3 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {searching && (
              <div className="absolute right-3 top-3 w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            )}
          </div>

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          {results.length > 0 && (
            <ul className="divide-y divide-slate-100 dark:divide-slate-700 border border-slate-100 dark:border-slate-700 rounded-xl overflow-hidden">
              {results.map((r) => {
                const already = subscribedIds.has(r.act_id);
                return (
                  <li key={r.act_id} className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{r.title}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {r.year && `${r.year} · `}
                        <code className="text-slate-400">{r.act_id}</code>
                      </p>
                    </div>
                    {r.url && (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 text-xs text-blue-500 hover:underline"
                      >
                        ISAP ↗
                      </a>
                    )}
                    <button
                      onClick={() => already ? undefined : void subscribe(r)}
                      disabled={already || adding === r.act_id || subs.length >= limit}
                      className={`shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                        already
                          ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 cursor-default"
                          : subs.length >= limit
                          ? "bg-slate-100 dark:bg-slate-700 text-slate-400 cursor-not-allowed"
                          : "bg-blue-600 text-white hover:bg-blue-700"
                      }`}
                    >
                      {adding === r.act_id ? "…" : already ? "✓ Obserwowany" : "+ Obserwuj"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {query.length >= 2 && !searching && results.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-4">
              Brak wyników. Spróbuj innej frazy lub bardziej szczegółowego zapytania.
            </p>
          )}
        </div>

        {/* Subscriptions list */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
            <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm">Twoje subskrypcje</h2>
            {tier === "free" && subs.length >= 4 && (
              <a href="/upgrade" className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                Zwiększ limit (Pro: 50) →
              </a>
            )}
          </div>

          {!subsLoaded ? (
            <div className="flex justify-center py-10">
              <div className="w-6 h-6 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            </div>
          ) : subs.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-sm">
              <p className="text-2xl mb-2">📋</p>
              <p>Brak subskrypcji. Wyszukaj akt prawny powyżej i kliknij „Obserwuj".</p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-700">
              {subs.map((sub) => (
                <li key={sub.id} className="px-5 py-4 flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{sub.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      <code>{sub.actId}</code>
                      {" · "}od {new Date(sub.createdAt).toLocaleDateString("pl-PL")}
                    </p>
                  </div>
                  {sub.url && (
                    <a
                      href={sub.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-xs text-blue-500 hover:underline"
                    >
                      ISAP ↗
                    </a>
                  )}
                  <button
                    onClick={() => void unsubscribe(sub.id)}
                    className="shrink-0 text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    Usuń
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Tier limits info */}
        <div className="bg-slate-50 dark:bg-slate-800/50 rounded-2xl border border-slate-200 dark:border-slate-700 p-5 text-xs text-slate-500 dark:text-slate-400 space-y-1">
          <p className="font-medium text-slate-600 dark:text-slate-300 text-sm">Limity subskrypcji</p>
          <p>Free: do 5 aktów · Pro: do 50 aktów · Kancelaria: bez limitu</p>
          <p>Powiadomienia email wysyłamy natychmiast po wykryciu zmiany w subskrybowanym akcie.</p>
        </div>
      </main>
    </div>
  );
}
