"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

interface Settings {
  email:             string | null;
  name:              string | null;
  tier:              string;
  newsletterEnabled: boolean;
  createdAt:         string;
}

const TIER_LABELS: Record<string, string> = {
  free:       "Free",
  pro:        "Pro",
  kancelaria: "Kancelaria",
};

export default function AccountSettingsPage() {
  const { data: session } = useSession();
  const [settings,  setSettings]  = useState<Settings | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState(false);
  const [saved,     setSaved]     = useState(false);

  useEffect(() => {
    fetch("/api/account/settings")
      .then((r) => r.json())
      .then((d: Settings) => { setSettings(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  async function toggleNewsletter() {
    if (!settings) return;
    setSaving(true);
    const next = !settings.newsletterEnabled;
    const res  = await fetch("/api/account/settings", {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ newsletterEnabled: next }),
    });
    if (res.ok) {
      setSettings((s) => s ? { ...s, newsletterEnabled: next } : s);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
    setSaving(false);
  }

  const tier = session?.user?.tier ?? settings?.tier ?? "free";

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Ustawienia konta</h1>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Profile info */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200">Profil</h2>
              <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
                <div className="flex justify-between">
                  <span>Email</span>
                  <span className="font-medium text-slate-800 dark:text-slate-200">{settings?.email ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Plan</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                    {TIER_LABELS[tier] ?? tier}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Konto od</span>
                  <span>{settings?.createdAt ? new Date(settings.createdAt).toLocaleDateString("pl-PL") : "—"}</span>
                </div>
              </div>
              {tier === "free" && (
                <a
                  href="/upgrade"
                  className="inline-block mt-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  Przejdź na Pro →
                </a>
              )}
            </div>

            {/* Newsletter toggle */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-semibold text-slate-800 dark:text-slate-200 mb-1">Newsletter</h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Tygodniowy digest zmian w prawie powiązanych z Twoimi pytaniami.
                    Wysyłamy go nie częściej niż raz w tygodniu, tylko jeśli są nowe alerty.
                  </p>
                </div>
                <button
                  onClick={toggleNewsletter}
                  disabled={saving}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${
                    settings?.newsletterEnabled
                      ? "bg-blue-600"
                      : "bg-slate-300 dark:bg-slate-600"
                  }`}
                  aria-checked={settings?.newsletterEnabled}
                  role="switch"
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      settings?.newsletterEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>
              {saved && (
                <p className="mt-3 text-xs text-green-600 dark:text-green-400">Zapisano.</p>
              )}
            </div>

            {/* Quick links */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-3">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200">Zarządzaj kontem</h2>
              <ul className="space-y-2 text-sm">
                <li>
                  <a href="/account/documents" className="text-blue-600 dark:text-blue-400 hover:underline">
                    Moje dokumenty (Private RAG) →
                  </a>
                </li>
                <li>
                  <a href="/account/api-tokens" className="text-blue-600 dark:text-blue-400 hover:underline">
                    Tokeny API →
                  </a>
                </li>
                <li>
                  <a href="/alerts" className="text-blue-600 dark:text-blue-400 hover:underline">
                    Alerty prawne →
                  </a>
                </li>
                {tier === "kancelaria" && (
                  <li>
                    <a href="/account/widget" className="text-blue-600 dark:text-blue-400 hover:underline">
                      Widget embed →
                    </a>
                  </li>
                )}
                {(tier === "pro" || tier === "kancelaria") && (
                  <li>
                    <a href="/api/stripe/portal" className="text-blue-600 dark:text-blue-400 hover:underline">
                      Portal rozliczeniowy Stripe →
                    </a>
                  </li>
                )}
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
