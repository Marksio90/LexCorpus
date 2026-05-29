"use client";

import { useState, useEffect, FormEvent } from "react";
import { useSession } from "next-auth/react";

interface ApiToken {
  id:           string;
  name:         string;
  prefix:       string;
  createdAt:    string;
  lastUsedAt:   string | null;
  requestCount: number;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pl-PL", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function ApiTokensPage() {
  const { data: session } = useSession();
  const [tokens,    setTokens]    = useState<ApiToken[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [name,      setName]      = useState("");
  const [creating,  setCreating]  = useState(false);
  const [newToken,  setNewToken]  = useState<string | null>(null);
  const [copied,    setCopied]    = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const isKancelaria = session?.user?.tier === "kancelaria";

  async function loadTokens() {
    const res = await fetch("/api/tokens");
    if (res.ok) setTokens(await res.json());
    setLoading(false);
  }

  useEffect(() => { void loadTokens(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    setNewToken(null);
    const res  = await fetch("/api/tokens", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ name }),
    });
    const data = await res.json() as { token?: string; error?: string };
    if (res.ok && data.token) {
      setNewToken(data.token);
      setName("");
      void loadTokens();
    } else {
      setError(data.error ?? "Błąd tworzenia tokenu.");
    }
    setCreating(false);
  }

  async function handleRevoke(id: string) {
    if (!confirm("Unieważnić ten token? Nie można cofnąć tej operacji.")) return;
    await fetch(`/api/tokens/${id}`, { method: "DELETE" });
    setTokens((t) => t.filter((tk) => tk.id !== id));
    if (newToken) setNewToken(null);
  }

  async function copyToken() {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Tokeny API</h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-8">

        {/* Blokada dla nie-kancelaria */}
        {!isKancelaria && (
          <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-2xl p-6 text-center">
            <p className="text-purple-800 dark:text-purple-200 font-semibold mb-2">
              Tokeny API dostępne w planie Kancelaria
            </p>
            <p className="text-sm text-purple-600 dark:text-purple-400 mb-4">
              Zintegruj LexCorpus bezpośrednio ze swoim systemem — CRM, workflow dokumentów, chatbot.
            </p>
            <a
              href="/upgrade"
              className="inline-block px-5 py-2 bg-purple-600 text-white rounded-xl text-sm font-medium hover:bg-purple-700 transition-colors"
            >
              Przejdź na plan Kancelaria
            </a>
          </div>
        )}

        {/* Nowy token — tylko dla kancelaria */}
        {isKancelaria && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
            <h2 className="font-semibold text-slate-900 dark:text-slate-100 mb-4">Utwórz nowy token</h2>

            <form onSubmit={handleCreate} className="flex gap-3">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="np. Produkcja CRM, Staging, Bot"
                required
                className="flex-1 px-4 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                disabled={creating || !name.trim()}
                className="px-5 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {creating ? "Tworzenie…" : "Utwórz"}
              </button>
            </form>

            {error && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
            )}

            {/* Nowy token — pokaż tylko raz */}
            {newToken && (
              <div className="mt-4 p-4 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700">
                <p className="text-xs font-semibold text-green-800 dark:text-green-300 mb-2 uppercase tracking-wide">
                  Skopiuj token — nie będzie widoczny ponownie
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-white dark:bg-slate-900 rounded-lg px-3 py-2 border border-green-200 dark:border-green-700 break-all font-mono text-green-800 dark:text-green-200">
                    {newToken}
                  </code>
                  <button
                    onClick={copyToken}
                    className="shrink-0 px-3 py-2 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 transition-colors"
                  >
                    {copied ? "Skopiowano ✓" : "Kopiuj"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Lista tokenów */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700">
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">
              Aktywne tokeny {tokens.length > 0 && <span className="text-slate-400 font-normal text-sm">({tokens.length}/10)</span>}
            </h2>
          </div>

          {loading ? (
            <div className="flex justify-center py-10">
              <div className="w-7 h-7 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            </div>
          ) : tokens.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-10">
              Brak tokenów. {isKancelaria ? "Utwórz pierwszy powyżej." : ""}
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-700">
              {tokens.map((tk) => (
                <li key={tk.id} className="px-6 py-4 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-800 dark:text-slate-200 text-sm">{tk.name}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 font-mono">
                      {tk.prefix}••••••••••••••••••••
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                      Utworzony: {formatDate(tk.createdAt)}
                      {" · "}
                      Ostatnie użycie: {formatDate(tk.lastUsedAt)}
                      {" · "}
                      {tk.requestCount} żądań
                    </p>
                  </div>
                  {isKancelaria && (
                    <button
                      onClick={() => handleRevoke(tk.id)}
                      className="shrink-0 text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors"
                    >
                      Unieważnij
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Dokumentacja użycia */}
        <div className="bg-slate-800 rounded-2xl p-6 text-sm">
          <h3 className="font-semibold text-white mb-4">Użycie API</h3>
          <pre className="text-slate-300 text-xs overflow-x-auto leading-relaxed">{`# Zadaj pytanie przez API
curl -X POST https://lexcorpus.pl/api/ask \\
  -H "Authorization: Bearer lxc_twój_token" \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Jakie są prawa pracownika?"}'

# Streaming (SSE)
curl -X POST https://lexcorpus.pl/api/ask/stream \\
  -H "Authorization: Bearer lxc_twój_token" \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Kiedy można wypowiedzieć umowę o pracę?"}'`}</pre>
        </div>

      </main>
    </div>
  );
}
