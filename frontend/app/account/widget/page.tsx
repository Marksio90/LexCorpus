"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

interface WidgetConfig {
  id:             string;
  token:          string;
  enabled:        boolean;
  title:          string;
  welcomeMsg:     string;
  accentColor:    string;
  logoUrl:        string | null;
  allowedDomains: string;
  requestCount:   number;
}

const BASE_URL = typeof window !== "undefined" ? window.location.origin : "";

export default function WidgetConfigPage() {
  const { data: session } = useSession();
  const tier = session?.user?.tier ?? "free";

  const [config,   setConfig]   = useState<WidgetConfig | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [saved,    setSaved]    = useState(false);
  const [copied,   setCopied]   = useState<"script" | "url" | null>(null);

  // Editable fields
  const [title,          setTitle]          = useState("Asystent prawny");
  const [welcomeMsg,     setWelcomeMsg]     = useState("Cześć! Jestem asystentem prawnym. W czym mogę pomóc?");
  const [accentColor,    setAccentColor]    = useState("#2563eb");
  const [logoUrl,        setLogoUrl]        = useState("");
  const [allowedDomains, setAllowedDomains] = useState("*");
  const [enabled,        setEnabled]        = useState(true);

  useEffect(() => {
    if (tier !== "kancelaria") { setLoading(false); return; }
    fetch("/api/widget/config")
      .then((r) => r.json())
      .then((d: WidgetConfig | null) => {
        setLoading(false);
        if (!d) return;
        setConfig(d);
        setTitle(d.title);
        setWelcomeMsg(d.welcomeMsg);
        setAccentColor(d.accentColor);
        setLogoUrl(d.logoUrl ?? "");
        setAllowedDomains(d.allowedDomains);
        setEnabled(d.enabled);
      })
      .catch(() => setLoading(false));
  }, [tier]);

  async function createWidget() {
    setSaving(true);
    const res = await fetch("/api/widget/config", { method: "POST" });
    const d   = await res.json() as WidgetConfig;
    setConfig(d);
    setSaving(false);
  }

  async function save() {
    setSaving(true);
    const res = await fetch("/api/widget/config", {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        title, welcomeMsg, accentColor,
        logoUrl:        logoUrl || null,
        allowedDomains, enabled,
      }),
    });
    const d = await res.json() as WidgetConfig;
    setConfig(d);
    setSaved(true);
    setSaving(false);
    setTimeout(() => setSaved(false), 2000);
  }

  function copy(text: string, which: "script" | "url") {
    void navigator.clipboard.writeText(text);
    setCopied(which);
    setTimeout(() => setCopied(null), 2000);
  }

  const scriptSnippet = config
    ? `<script src="${BASE_URL}/widget/${config.token}/embed.js" defer></script>`
    : "";
  const iframeUrl = config ? `${BASE_URL}/widget/${config.token}` : "";

  if (tier !== "kancelaria") {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-10 max-w-md text-center">
          <p className="text-2xl mb-3">🏢</p>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Plan Kancelaria</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
            Widget embed dostępny wyłącznie w planie Kancelaria. Wgraj chatbota na własną stronę z pełnym white-labelingiem.
          </p>
          <a href="/upgrade" className="inline-block px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors">
            Zobacz plan Kancelaria →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Widget embed</h1>
          {config && (
            <span className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium ${
              enabled
                ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
                : "bg-slate-100 dark:bg-slate-700 text-slate-500"
            }`}>
              {enabled ? "Aktywny" : "Wyłączony"}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : !config ? (
          /* First time — create widget */
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-10 text-center">
            <p className="text-3xl mb-3">🤖</p>
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Utwórz widget</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
              Wygeneruj unikalny token i wgraj chatbot prawny na swoją stronę jedną linią kodu.
            </p>
            <button
              onClick={createWidget}
              disabled={saving}
              className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Tworzenie…" : "Utwórz widget →"}
            </button>
          </div>
        ) : (
          <>
            {/* Embed snippet */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200">Kod do wklejenia</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Wklej ten znacznik przed zamykającym tagiem <code className="text-xs bg-slate-100 dark:bg-slate-700 px-1 rounded">&lt;/body&gt;</code> na swojej stronie:
              </p>
              <div className="relative">
                <pre className="bg-slate-900 text-green-400 text-xs rounded-xl p-4 overflow-x-auto font-mono">
                  {scriptSnippet}
                </pre>
                <button
                  onClick={() => copy(scriptSnippet, "script")}
                  className="absolute top-2 right-2 text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                >
                  {copied === "script" ? "✓ Skopiowano" : "Kopiuj"}
                </button>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <p className="text-xs text-slate-500 dark:text-slate-400">Lub użyj jako iframe:</p>
                <code className="text-xs text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded truncate max-w-xs">
                  {iframeUrl}
                </code>
                <button
                  onClick={() => copy(iframeUrl, "url")}
                  className="shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {copied === "url" ? "✓" : "Kopiuj URL"}
                </button>
                <a
                  href={iframeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Podgląd ↗
                </a>
              </div>

              <p className="text-xs text-slate-400">
                Użycia: <strong>{config.requestCount}</strong> zapytań
              </p>
            </div>

            {/* Config form */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-5">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200">Konfiguracja</h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Tytuł chatbota">
                  <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className={inputCls}
                    placeholder="Asystent prawny"
                  />
                </Field>

                <Field label="Kolor akcentu">
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={accentColor}
                      onChange={(e) => setAccentColor(e.target.value)}
                      className="w-10 h-9 rounded-lg border border-slate-200 dark:border-slate-600 cursor-pointer p-0.5"
                    />
                    <input
                      value={accentColor}
                      onChange={(e) => setAccentColor(e.target.value)}
                      className={`${inputCls} flex-1`}
                      placeholder="#2563eb"
                    />
                  </div>
                </Field>

                <Field label="Wiadomość powitalna" className="sm:col-span-2">
                  <textarea
                    value={welcomeMsg}
                    onChange={(e) => setWelcomeMsg(e.target.value)}
                    rows={2}
                    className={`${inputCls} resize-none`}
                    placeholder="Cześć! Jestem asystentem prawnym…"
                  />
                </Field>

                <Field label="URL logo (opcjonalnie)">
                  <input
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    className={inputCls}
                    placeholder="https://twoja-firma.pl/logo.png"
                  />
                </Field>

                <Field label="Dozwolone domeny">
                  <input
                    value={allowedDomains}
                    onChange={(e) => setAllowedDomains(e.target.value)}
                    className={inputCls}
                    placeholder="* (wszystkie) lub twoja-firma.pl, kancelaria.pl"
                  />
                  <p className="text-xs text-slate-400 mt-1">Oddziel przecinkami lub wpisz * dla wszystkich</p>
                </Field>
              </div>

              {/* Enable toggle */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-700">
                <div>
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Widget aktywny</p>
                  <p className="text-xs text-slate-400">Wyłącz tymczasowo bez usuwania konfiguracji</p>
                </div>
                <button
                  onClick={() => setEnabled((v) => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    enabled ? "bg-blue-600" : "bg-slate-300 dark:bg-slate-600"
                  }`}
                  role="switch"
                  aria-checked={enabled}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    enabled ? "translate-x-6" : "translate-x-1"
                  }`} />
                </button>
              </div>

              <button
                onClick={save}
                disabled={saving}
                className="mt-2 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {saving ? "Zapisywanie…" : saved ? "✓ Zapisano" : "Zapisz zmiany"}
              </button>
            </div>

            {/* Live preview */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700">
                <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm">Podgląd na żywo</h2>
              </div>
              <iframe
                src={iframeUrl}
                className="w-full"
                style={{ height: "460px", border: "none", display: "block" }}
                title="Widget preview"
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const inputCls =
  "w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500";

function Field({
  label, children, className = "",
}: {
  label: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">{label}</label>
      {children}
    </div>
  );
}
