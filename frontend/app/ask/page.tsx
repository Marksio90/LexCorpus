"use client";

import { useState, useCallback } from "react";
import { AskForm } from "@/components/AskForm";
import { AnswerCard } from "@/components/AnswerCard";
import { Sidebar } from "@/components/Sidebar";
import { askQuestion } from "@/lib/api";
import { saveToHistory } from "@/lib/history";
import type { AskResponse } from "@/lib/types";

export default function AskPage() {
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleAsk = useCallback(async (question: string) => {
    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await askQuestion(question, 5);
      setResponse(result);
      saveToHistory(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wystąpił nieoczekiwany błąd.");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelectHistory = useCallback((question: string) => {
    setSidebarOpen(false);
    handleAsk(question);
  }, [handleAsk]);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelectQuestion={handleSelectHistory}
      />

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            aria-label="Otwórz historię"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-blue-600 dark:text-blue-400">⚖️</span>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">LexCorpus</h1>
            <span className="hidden sm:inline text-sm text-slate-500 dark:text-slate-400">
              — Polski AI Prawny
            </span>
          </div>
          <div className="ml-auto flex gap-2">
            <a
              href="/history"
              className="text-sm text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            >
              Historia
            </a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <a
              href="/admin"
              className="text-sm text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            >
              Admin
            </a>
          </div>
        </header>

        {/* Content area */}
        <main className="flex-1 overflow-y-auto px-4 py-6 max-w-4xl mx-auto w-full">
          {/* Hero / intro */}
          {!response && !loading && !error && (
            <div className="mb-8 text-center">
              <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-200 mb-2">
                Zapytaj o polskie prawo
              </h2>
              <p className="text-slate-500 dark:text-slate-400 max-w-xl mx-auto">
                System przeszukuje akty prawne z ISAP i generuje odpowiedź na podstawie
                obowiązujących przepisów prawa polskiego.
              </p>
            </div>
          )}

          {/* Ask form */}
          <AskForm onSubmit={handleAsk} loading={loading} />

          {/* Error */}
          {error && (
            <div className="mt-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300">
              <p className="font-semibold">Błąd</p>
              <p className="text-sm mt-1">{error}</p>
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="mt-8 flex flex-col items-center gap-3 text-slate-500 dark:text-slate-400">
              <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
              <p className="text-sm">Przeszukuję akty prawne i generuję odpowiedź…</p>
            </div>
          )}

          {/* Answer */}
          {response && !loading && (
            <div className="mt-6">
              <AnswerCard response={response} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
