"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

interface ExpertRequest {
  id:          string;
  question:    string;
  context:     string | null;
  status:      "open" | "answered" | "closed";
  response:    string | null;
  respondedAt: string | null;
  createdAt:   string;
  requester?:  { name: string | null };
  expert?:     { name: string | null };
}

const STATUS_META = {
  open:     { label: "Otwarte",    color: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300",  dot: "bg-amber-400" },
  answered: { label: "Odpowiedź", color: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300",  dot: "bg-green-500" },
  closed:   { label: "Zamknięte", color: "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400",     dot: "bg-slate-300 dark:bg-slate-600" },
};

export default function ExpertPage() {
  const { data: session } = useSession();
  const tier = session?.user?.tier ?? "free";
  const isExpert = tier === "kancelaria";

  const [tab,      setTab]      = useState<"mine" | "expert">(isExpert ? "expert" : "mine");
  const [requests, setRequests] = useState<ExpertRequest[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [question, setQuestion] = useState("");
  const [context,  setContext]  = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [response, setResponse] = useState<Record<string, string>>({});
  const [responding, setResponding] = useState<string | null>(null);

  async function loadRequests(t: "mine" | "expert") {
    setLoading(true);
    const res  = await fetch(`/api/expert/requests?role=${t === "expert" ? "expert" : "mine"}`);
    const data = await res.json() as ExpertRequest[];
    setRequests(Array.isArray(data) ? data : []);
    setLoading(false);
  }

  useEffect(() => { void loadRequests(tab); }, [tab]);

  async function submit() {
    if (!question.trim()) return;
    setSubmitting(true);
    setError(null);
    const res  = await fetch("/api/expert/requests", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ question, context }),
    });
    const data = await res.json() as ExpertRequest & { error?: string };
    if (!res.ok) { setError(data.error ?? "Błąd."); }
    else {
      setRequests((prev) => [data, ...prev]);
      setQuestion("");
      setContext("");
    }
    setSubmitting(false);
  }

  async function respond(id: string) {
    const resp = response[id]?.trim();
    if (!resp) return;
    setResponding(id);
    const res  = await fetch(`/api/expert/requests/${id}`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ response: resp }),
    });
    const data = await res.json() as ExpertRequest;
    setRequests((prev) => prev.map((r) => r.id === id ? data : r));
    setResponse((p) => { const n = { ...p }; delete n[id]; return n; });
    setResponding(null);
  }

  async function closeRequest(id: string) {
    await fetch(`/api/expert/requests/${id}`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ status: "closed" }),
    });
    setRequests((prev) => prev.map((r) => r.id === id ? { ...r, status: "closed" } : r));
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Zapytaj eksperta</h1>
          {isExpert && (
            <div className="ml-auto flex gap-1 bg-slate-100 dark:bg-slate-700 p-1 rounded-xl">
              {(["mine", "expert"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                    tab === t
                      ? "bg-white dark:bg-slate-600 text-slate-800 dark:text-slate-100 shadow-sm"
                      : "text-slate-500 dark:text-slate-400"
                  }`}
                >
                  {t === "mine" ? "Moje pytania" : "Panel eksperta"}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">

        {/* Submit form — only on "mine" tab */}
        {tab === "mine" && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800 dark:text-slate-200 mb-1">Zadaj pytanie ekspertowi</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Licencjonowani prawnicy (plan Kancelaria) odpowiedzą na Twoje pytanie prawne.
                Odpowiedź dostaniesz e-mailem.
              </p>
            </div>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              placeholder="Opisz swój problem prawny szczegółowo…"
              className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                Kontekst / odpowiedź AI (opcjonalnie)
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                rows={2}
                placeholder="Wklej odpowiedź AI której nie jesteś pewien, lub dodatkowe informacje…"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>
            {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
            <button
              onClick={submit}
              disabled={submitting || !question.trim()}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {submitting ? "Wysyłanie…" : "Wyślij do eksperta →"}
            </button>
          </div>
        )}

        {/* Requests list */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : requests.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-sm">
            <p className="text-2xl mb-2">💬</p>
            <p>{tab === "expert" ? "Brak otwartych pytań." : "Nie masz jeszcze żadnych pytań do ekspertów."}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {requests.map((r) => {
              const sm = STATUS_META[r.status];
              return (
                <div key={r.id} className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5 space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1 ${sm.color}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${sm.dot}`} />
                          {sm.label}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(r.createdAt).toLocaleDateString("pl-PL")}
                        </span>
                        {tab === "expert" && r.requester?.name && (
                          <span className="text-xs text-slate-400">{r.requester.name}</span>
                        )}
                      </div>
                      <p className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed">{r.question}</p>
                      {r.context && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 italic">Kontekst: {r.context.slice(0, 150)}{r.context.length > 150 ? "…" : ""}</p>
                      )}
                    </div>
                  </div>

                  {/* Expert response */}
                  {r.response && (
                    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-4">
                      <p className="text-xs font-semibold text-green-700 dark:text-green-300 mb-1">
                        Odpowiedź eksperta {r.respondedAt ? `· ${new Date(r.respondedAt).toLocaleDateString("pl-PL")}` : ""}
                      </p>
                      <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{r.response}</p>
                    </div>
                  )}

                  {/* Expert response form */}
                  {tab === "expert" && r.status === "open" && (
                    <div className="space-y-2">
                      <textarea
                        value={response[r.id] ?? ""}
                        onChange={(e) => setResponse((p) => ({ ...p, [r.id]: e.target.value }))}
                        rows={3}
                        placeholder="Wpisz swoją odpowiedź…"
                        className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                      />
                      <button
                        onClick={() => void respond(r.id)}
                        disabled={responding === r.id || !response[r.id]?.trim()}
                        className="px-4 py-2 bg-green-600 text-white rounded-xl text-xs font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors"
                      >
                        {responding === r.id ? "Wysyłanie…" : "Wyślij odpowiedź"}
                      </button>
                    </div>
                  )}

                  {/* Close button for requester */}
                  {tab === "mine" && r.status !== "closed" && (
                    <button
                      onClick={() => void closeRequest(r.id)}
                      className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                    >
                      Zamknij zapytanie
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
