"use client";

import { useState, useRef } from "react";
import {
  DocumentAnalysis, REKOMENDACJA_META, POWAGA_META, RedFlag,
} from "@/lib/analysis-types";

type Status = "idle" | "analyzing" | "done" | "error";

export default function AnalyzePage() {
  const [status,   setStatus]   = useState<Status>("idle");
  const [file,     setFile]     = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rawJson,  setRawJson]  = useState("");
  const [result,   setResult]   = useState<DocumentAnalysis | null>(null);
  const [error,    setError]    = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function pickFile(f: File) {
    setFile(f);
    setResult(null);
    setRawJson("");
    setError(null);
    setStatus("idle");
  }

  async function analyze() {
    if (!file) return;
    setStatus("analyzing");
    setRawJson("");
    setResult(null);
    setError(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      if (!res.ok) {
        const d = await res.json() as { error?: string };
        setError(d.error ?? "Błąd analizy.");
        setStatus("error");
        return;
      }

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let json = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6)) as { delta?: string; done?: boolean; error?: string };
          if (data.error) { setError(data.error); setStatus("error"); return; }
          if (data.delta) {
            json += data.delta;
            setRawJson(json);
          }
          if (data.done) {
            try {
              const parsed = JSON.parse(json) as DocumentAnalysis;
              setResult(parsed);
              setStatus("done");
            } catch {
              setError("Nie udało się sparsować odpowiedzi AI.");
              setStatus("error");
            }
          }
        }
      }
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Analiza dokumentu</h1>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Upload zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault(); setDragOver(false);
            const f = e.dataTransfer.files[0];
            if (f) pickFile(f);
          }}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-10 text-center transition-colors cursor-pointer ${
            dragOver
              ? "border-blue-400 bg-blue-50 dark:bg-blue-900/20"
              : file
              ? "border-blue-400 bg-blue-50/50 dark:bg-blue-900/10"
              : "border-slate-300 dark:border-slate-600 hover:border-blue-300 bg-white dark:bg-slate-800"
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); }}
          />
          {file ? (
            <div className="flex flex-col items-center gap-2">
              <span className="text-3xl">{file.type === "application/pdf" ? "📄" : "🖼️"}</span>
              <p className="font-medium text-slate-800 dark:text-slate-200">{file.name}</p>
              <p className="text-sm text-slate-400">{(file.size / 1024).toFixed(0)} KB · kliknij aby zmienić</p>
            </div>
          ) : (
            <>
              <svg className="w-12 h-12 mx-auto mb-3 text-slate-300 dark:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="font-medium text-slate-700 dark:text-slate-300">Przeciągnij dokument lub kliknij</p>
              <p className="text-sm text-slate-400 mt-1">PDF (z tekstem), JPG, PNG, WEBP · max 10 MB</p>
            </>
          )}
        </div>

        {file && status !== "analyzing" && (
          <button
            onClick={analyze}
            disabled={false}
            className="w-full py-3 bg-blue-600 text-white rounded-2xl font-semibold text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            🔍 Analizuj dokument
          </button>
        )}

        {status === "analyzing" && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-center">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mx-auto mb-4" />
            <p className="font-medium text-slate-700 dark:text-slate-300">AI analizuje dokument…</p>
            <p className="text-sm text-slate-400 mt-1">Zazwyczaj zajmuje to 10–20 sekund</p>
            {rawJson.length > 10 && (
              <p className="text-xs text-slate-400 mt-3 font-mono">
                {rawJson.length} znaków odpowiedzi…
              </p>
            )}
          </div>
        )}

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {result && <AnalysisResult result={result} />}
      </main>
    </div>
  );
}

function AnalysisResult({ result }: { result: DocumentAnalysis }) {
  const rec = REKOMENDACJA_META[result.rekomendacja] ?? REKOMENDACJA_META.skonsultować_z_prawnikiem;

  const highFlags  = result.czerwone_flagi.filter((f) => f.powaga === "wysoka");
  const otherFlags = result.czerwone_flagi.filter((f) => f.powaga !== "wysoka");

  return (
    <div className="space-y-4">
      {/* Header card */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Typ dokumentu</p>
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">{result.typ_dokumentu}</h2>
          </div>
          <div className={`shrink-0 px-4 py-2 rounded-xl border font-semibold text-sm ${rec.bg} ${rec.color}`}>
            {rec.label}
          </div>
        </div>

        <p className="mt-4 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">{result.podsumowanie}</p>

        {result.strony.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {result.strony.map((s, i) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Red flags */}
      {result.czerwone_flagi.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
            <span className="text-red-500">⚠</span>
            <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-sm">
              Czerwone flagi ({result.czerwone_flagi.length})
            </h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {[...highFlags, ...otherFlags].map((flag: RedFlag, i) => {
              const m = POWAGA_META[flag.powaga] ?? POWAGA_META.niska;
              return (
                <li key={i} className="px-5 py-4">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-2 h-2 rounded-full ${m.dot}`} />
                    <span className={`text-xs font-semibold ${m.text}`}>{m.label} powaga</span>
                  </div>
                  <p className="text-sm text-slate-700 dark:text-slate-300 mb-1">{flag.opis}</p>
                  {flag.fragment && (
                    <blockquote className="text-xs text-slate-500 dark:text-slate-400 italic border-l-2 border-slate-200 dark:border-slate-600 pl-3">
                      „{flag.fragment}"
                    </blockquote>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Dates + obligations — 2 col */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Dates */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-3">📅 Daty</h3>
          <dl className="space-y-1.5 text-sm">
            {result.daty.zawarcia && <DateRow label="Zawarcie" val={result.daty.zawarcia} />}
            {result.daty.obowiazywania_od && <DateRow label="Obowiązuje od" val={result.daty.obowiazywania_od} />}
            {result.daty.obowiazywania_do && <DateRow label="Obowiązuje do" val={result.daty.obowiazywania_do} />}
            {result.daty.inne?.map((d, i) => <DateRow key={i} label="Inne" val={d} />)}
            {!result.daty.zawarcia && !result.daty.obowiazywania_od && !result.daty.obowiazywania_do && (result.daty.inne?.length ?? 0) === 0 && (
              <p className="text-slate-400 text-xs">Nie znaleziono dat</p>
            )}
          </dl>
        </div>

        {/* Obligations */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-3">📋 Zobowiązania</h3>
          {result.strony.slice(0, 2).map((strona, si) => {
            const items = si === 0 ? result.zobowiazania.strona_1 : result.zobowiazania.strona_2;
            return items?.length ? (
              <div key={si} className="mb-3 last:mb-0">
                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">{strona}</p>
                <ul className="space-y-0.5">
                  {items.map((item, ii) => (
                    <li key={ii} className="text-xs text-slate-600 dark:text-slate-400 flex gap-1.5">
                      <span className="text-slate-300 mt-0.5">•</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null;
          })}
        </div>
      </div>

      {/* Key provisions */}
      {result.kluczowe_postanowienia.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-3">📌 Kluczowe postanowienia</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {result.kluczowe_postanowienia.map((p, i) => (
              <div key={i} className="bg-slate-50 dark:bg-slate-700/50 rounded-xl px-4 py-3">
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-0.5">{p.tytuł}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{p.treść}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-slate-400 text-center px-4">
        Analiza wygenerowana przez AI. Nie stanowi porady prawnej. Skonsultuj ważne dokumenty z licencjonowanym prawnikiem.
      </p>
    </div>
  );
}

function DateRow({ label, val }: { label: string; val: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-slate-500 dark:text-slate-400 shrink-0">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-200 text-right">{val}</dd>
    </div>
  );
}
