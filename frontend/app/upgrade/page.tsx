"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";

const PLANS = [
  {
    key:         "free",
    name:        "Free",
    price:       "0 zł",
    period:      "",
    description: "Dla osób, które chcą sprawdzić system",
    features:    ["20 zapytań / dzień", "Pełny dostęp do historii", "Wyszukiwanie dokumentów", "Cytowania z ISAP/SAOS"],
    cta:         null,
    highlight:   false,
    color:       "slate",
  },
  {
    key:         "pro",
    name:        "Pro",
    price:       "49 zł",
    period:      "/ miesiąc",
    description: "Dla prawników i aplikantów",
    features:    ["500 zapytań / dzień", "Eksport PDF i Markdown", "Tryb porównania źródeł", "Priorytetowe odpowiedzi", "Wsparcie e-mail"],
    cta:         "Wybierz Pro",
    highlight:   true,
    color:       "blue",
  },
  {
    key:         "kancelaria",
    name:        "Kancelaria",
    price:       "299 zł",
    period:      "/ miesiąc",
    description: "Dla kancelarii i działów prawnych",
    features:    ["Nieograniczone zapytania", "Dostęp do API (tokeny)", "5 kont użytkowników", "SLA 99,9%", "Dedykowana instancja on-premise (opcja)", "Priorytetowe wsparcie"],
    cta:         "Skontaktuj się",
    highlight:   false,
    color:       "purple",
  },
] as const;

export default function UpgradePage() {
  const { data: session } = useSession();
  const currentTier = session?.user?.tier ?? "free";
  const [loading, setLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpgrade(plan: string) {
    setLoading(plan);
    setError(null);
    try {
      const res  = await fetch("/api/stripe/checkout", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ plan }),
      });
      const data = await res.json() as { url?: string; error?: string };
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError(data.error ?? "Błąd tworzenia sesji płatności.");
      }
    } catch {
      setError("Błąd połączenia. Spróbuj ponownie.");
    } finally {
      setLoading(null);
    }
  }

  async function handlePortal() {
    setPortalLoading(true);
    setError(null);
    try {
      const res  = await fetch("/api/stripe/portal", { method: "POST" });
      const data = await res.json() as { url?: string; error?: string };
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError(data.error ?? "Błąd otwierania portalu.");
      }
    } catch {
      setError("Błąd połączenia.");
    } finally {
      setPortalLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Plany i cennik</h1>
          </div>
          {currentTier !== "free" && (
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="text-sm text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors disabled:opacity-50"
            >
              {portalLoading ? "Przekierowanie…" : "Zarządzaj subskrypcją →"}
            </button>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-12">
        {/* Hero */}
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-3">
            Wybierz swój plan
          </h2>
          <p className="text-slate-500 dark:text-slate-400 max-w-xl mx-auto">
            Wszystkie plany dają dostęp do 636 000 dokumentów prawnych — ustaw swój limit zapytań.
          </p>
        </div>

        {error && (
          <div className="mb-8 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300 text-sm text-center">
            {error}
          </div>
        )}

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => {
            const isCurrent = currentTier === plan.key;
            const isHighlight = plan.highlight;

            return (
              <div
                key={plan.key}
                className={`relative rounded-2xl border p-6 flex flex-col ${
                  isHighlight
                    ? "bg-blue-600 border-blue-600 text-white shadow-xl shadow-blue-200 dark:shadow-blue-900/40 scale-105"
                    : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700"
                }`}
              >
                {isHighlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-yellow-400 text-yellow-900 text-xs font-bold px-3 py-1 rounded-full">
                      NAJPOPULARNIEJSZY
                    </span>
                  </div>
                )}

                <div className="mb-4">
                  <h3 className={`text-lg font-bold mb-1 ${isHighlight ? "text-white" : "text-slate-900 dark:text-slate-100"}`}>
                    {plan.name}
                  </h3>
                  <div className="flex items-baseline gap-1">
                    <span className={`text-3xl font-bold ${isHighlight ? "text-white" : "text-slate-900 dark:text-slate-100"}`}>
                      {plan.price}
                    </span>
                    <span className={`text-sm ${isHighlight ? "text-blue-200" : "text-slate-400"}`}>
                      {plan.period}
                    </span>
                  </div>
                  <p className={`text-sm mt-1 ${isHighlight ? "text-blue-100" : "text-slate-500 dark:text-slate-400"}`}>
                    {plan.description}
                  </p>
                </div>

                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <svg className={`w-4 h-4 mt-0.5 shrink-0 ${isHighlight ? "text-blue-200" : "text-green-500"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className={isHighlight ? "text-blue-50" : "text-slate-600 dark:text-slate-300"}>{f}</span>
                    </li>
                  ))}
                </ul>

                {isCurrent ? (
                  <div className={`text-center py-2.5 rounded-xl text-sm font-medium border ${
                    isHighlight
                      ? "border-blue-300 text-blue-100"
                      : "border-slate-200 dark:border-slate-600 text-slate-400 dark:text-slate-500"
                  }`}>
                    Twój aktualny plan
                  </div>
                ) : plan.cta === null ? (
                  <div className="text-center py-2.5 rounded-xl text-sm text-slate-400 border border-slate-200 dark:border-slate-700">
                    Darmowy, zawsze
                  </div>
                ) : plan.key === "kancelaria" ? (
                  <a
                    href="mailto:kontakt@lexcorpus.pl?subject=Plan Kancelaria"
                    className="block text-center py-2.5 rounded-xl text-sm font-medium bg-purple-600 hover:bg-purple-700 text-white transition-colors"
                  >
                    {plan.cta}
                  </a>
                ) : (
                  <button
                    onClick={() => handleUpgrade(plan.key)}
                    disabled={loading === plan.key}
                    className={`py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-60 ${
                      isHighlight
                        ? "bg-white text-blue-600 hover:bg-blue-50"
                        : "bg-blue-600 text-white hover:bg-blue-700"
                    }`}
                  >
                    {loading === plan.key ? "Przekierowanie…" : plan.cta}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="mt-16 max-w-2xl mx-auto space-y-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-6 text-center">Najczęstsze pytania</h3>
          {[
            ["Czy mogę anulować w dowolnym momencie?", "Tak. Subskrypcja działa do końca opłaconego okresu, potem automatycznie wraca do planu Free."],
            ["Czy dane są aktualne?", "Orzecznictwo SAOS jest synchronizowane co tydzień. Ustawy z ISAP — na bieżąco."],
            ["Jak wygląda płatność?", "Obsługujemy karty płatnicze przez Stripe. Faktura VAT dostępna w portalu klienta."],
            ["Co jeśli przekroczę limit zapytań?", "Zapytanie zostanie zablokowane z komunikatem. Możesz od razu przejść na wyższy plan."],
          ].map(([q, a]) => (
            <div key={q} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <p className="font-medium text-slate-900 dark:text-slate-100 mb-1">{q}</p>
              <p className="text-sm text-slate-500 dark:text-slate-400">{a}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
