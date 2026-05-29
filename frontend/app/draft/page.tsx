"use client";

import { useState, useRef } from "react";
import { useSession } from "next-auth/react";
import { DRAFT_TEMPLATES, DraftTemplate } from "@/lib/draft-templates";
import dynamic from "next/dynamic";

const DraftPdfButton = dynamic(() => import("@/components/DraftPdfButton"), { ssr: false });

export default function DraftPage() {
  const { data: session } = useSession();
  const tier = session?.user?.tier ?? "free";

  const [selected,  setSelected]  = useState<DraftTemplate | null>(null);
  const [fields,    setFields]    = useState<Record<string, string>>({});
  const [document,  setDocument]  = useState("");
  const [generating, setGenerating] = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function selectTemplate(t: DraftTemplate) {
    if (t.tier === "pro" && tier === "free") return; // locked
    setSelected(t);
    setFields({});
    setDocument("");
    setError(null);
  }

  async function generate() {
    if (!selected) return;
    setError(null);
    setDocument("");
    setGenerating(true);

    try {
      const res = await fetch("/api/draft", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ templateId: selected.id, fields }),
      });

      if (!res.ok) {
        const d = await res.json() as { error?: string };
        setError(d.error ?? "Błąd generowania.");
        setGenerating(false);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6)) as { delta?: string; done?: boolean; error?: string };
          if (data.error) { setError(data.error); break; }
          if (data.delta) setDocument((prev) => prev + data.delta);
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  const requiredFilled = selected?.fields
    .filter((f) => f.required)
    .every((f) => (fields[f.key] ?? "").trim() !== "") ?? false;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Kreator dokumentów</h1>
          <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
            powered by {process.env.NEXT_PUBLIC_MODEL_LABEL ?? "GPT-4o-mini"}
          </span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">

          {/* Left: template picker */}
          <div className="space-y-3">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-1">
              Wybierz szablon
            </p>
            {DRAFT_TEMPLATES.map((t) => {
              const locked = t.tier === "pro" && tier === "free";
              const active = selected?.id === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => selectTemplate(t)}
                  disabled={locked}
                  className={`w-full text-left px-4 py-3 rounded-2xl border transition-all ${
                    active
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                      : locked
                      ? "border-slate-200 dark:border-slate-700 opacity-50 cursor-not-allowed bg-white dark:bg-slate-800"
                      : "border-slate-200 dark:border-slate-700 hover:border-blue-300 bg-white dark:bg-slate-800"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl leading-none mt-0.5">{t.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className={`font-medium text-sm truncate ${active ? "text-blue-700 dark:text-blue-300" : "text-slate-800 dark:text-slate-200"}`}>
                          {t.label}
                        </p>
                        {t.tier === "pro" && (
                          <span className="shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-semibold">
                            Pro
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 leading-snug">{t.description}</p>
                    </div>
                  </div>
                </button>
              );
            })}

            {tier === "free" && (
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl p-4 text-center">
                <p className="text-xs text-blue-700 dark:text-blue-300 mb-2 font-medium">
                  4 szablony dostępne w planie Pro
                </p>
                <a
                  href="/upgrade"
                  className="inline-block px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors"
                >
                  Przejdź na Pro →
                </a>
              </div>
            )}
          </div>

          {/* Right: form + result */}
          <div className="space-y-4">
            {!selected ? (
              <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-10 text-center text-slate-400">
                <svg className="w-12 h-12 mx-auto mb-3 text-slate-200 dark:text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="font-medium text-sm">Wybierz szablon z listy</p>
                <p className="text-xs mt-1">Wypełnisz formularz, AI wygeneruje gotowy dokument</p>
              </div>
            ) : (
              <>
                {/* Form */}
                <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
                  <h2 className="font-semibold text-slate-800 dark:text-slate-200">{selected.icon} {selected.label}</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {selected.fields.map((field) => (
                      <div key={field.key} className={field.type === "textarea" ? "sm:col-span-2" : ""}>
                        <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                          {field.label}
                          {field.required && <span className="text-red-500 ml-0.5">*</span>}
                        </label>
                        {field.type === "textarea" ? (
                          <textarea
                            value={fields[field.key] ?? ""}
                            onChange={(e) => setFields((f) => ({ ...f, [field.key]: e.target.value }))}
                            placeholder={field.placeholder}
                            rows={3}
                            className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                          />
                        ) : field.type === "select" ? (
                          <select
                            value={fields[field.key] ?? ""}
                            onChange={(e) => setFields((f) => ({ ...f, [field.key]: e.target.value }))}
                            className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="">— wybierz —</option>
                            {field.options?.map((o) => (
                              <option key={o} value={o}>{o}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type={field.type}
                            value={fields[field.key] ?? ""}
                            onChange={(e) => setFields((f) => ({ ...f, [field.key]: e.target.value }))}
                            placeholder={field.placeholder}
                            className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        )}
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={generate}
                    disabled={generating || !requiredFilled}
                    className="mt-2 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    {generating ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                        Generowanie…
                      </>
                    ) : (
                      "✨ Generuj dokument"
                    )}
                  </button>
                </div>

                {/* Error */}
                {error && (
                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
                    {error}
                  </div>
                )}

                {/* Result */}
                {(document || generating) && (
                  <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-slate-700">
                      <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">Wygenerowany dokument</span>
                      <div className="flex items-center gap-2">
                        {document && (
                          <>
                            <button
                              onClick={() => { void navigator.clipboard.writeText(document); }}
                              className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
                            >
                              Kopiuj
                            </button>
                            <DraftPdfButton text={document} filename={selected.label} />
                          </>
                        )}
                      </div>
                    </div>
                    <div className="relative">
                      <textarea
                        ref={textareaRef}
                        value={document}
                        onChange={(e) => setDocument(e.target.value)}
                        className="w-full px-6 py-5 text-sm font-mono text-slate-800 dark:text-slate-200 bg-transparent border-none focus:outline-none resize-none leading-relaxed"
                        rows={Math.max(20, document.split("\n").length + 3)}
                        placeholder={generating ? "Generowanie…" : ""}
                        spellCheck={false}
                      />
                      {generating && (
                        <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse absolute bottom-6 left-6" style={{ marginLeft: `${(document.split("\n").at(-1)?.length ?? 0) * 7.2}px` }} />
                      )}
                    </div>
                    {document && (
                      <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-700 text-xs text-slate-400 dark:text-slate-500">
                        Możesz edytować dokument bezpośrednio powyżej przed pobraniem.
                        Zawsze skonsultuj ważne dokumenty z prawnikiem.
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
