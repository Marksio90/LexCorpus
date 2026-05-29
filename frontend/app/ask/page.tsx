"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { AskForm } from "@/components/AskForm";
import { AnswerCard } from "@/components/AnswerCard";
import { Sidebar } from "@/components/Sidebar";
import { UsageBar } from "@/components/UsageBar";
import { AlertsBadge } from "@/components/AlertsBadge";
import { askQuestionStream } from "@/lib/api";
import { saveToHistory } from "@/lib/history";
import type { AskResponse, AnswerConfidence, ConversationTurn, SourceDocument, SourceType } from "@/lib/types";

export default function AskPage() {
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [history, setHistory] = useState<ConversationTurn[]>([]);

  // Refs to accumulate streaming state without stale closures
  const answerRef = useRef("");
  const sourcesRef = useRef<SourceDocument[]>([]);
  const retrievalRef = useRef(false);
  const confidenceRef = useRef<AnswerConfidence | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  // Cleanup any in-flight stream when component unmounts
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const handleAsk = useCallback(async (question: string, sourceType?: SourceType | null) => {
    // Cancel any previous in-flight request
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const { signal } = abortRef.current;

    setLoading(true);
    setError(null);
    setResponse(null);
    setStreamingText(null);
    answerRef.current = "";
    sourcesRef.current = [];
    retrievalRef.current = false;
    confidenceRef.current = undefined;

    try {
      // Sprawdź i inkrementuj dzienny limit
      const usageRes = await fetch("/api/usage", { method: "POST", signal });
      if (usageRes.status === 429) {
        const data = await usageRes.json();
        setError(data.error + ` (${data.used}/${data.limit}). Przejdź na plan Pro aby kontynuować.`);
        setLoading(false);
        return;
      }

      await askQuestionStream(question, 5, {
        onSources(sources, retrievalUsed) {
          sourcesRef.current = sources;
          retrievalRef.current = retrievalUsed;
          // Show empty streaming card immediately so sources appear while text streams
          setStreamingText("");
        },
        onDelta(text) {
          answerRef.current += text;
          setStreamingText(answerRef.current);
        },
        onDone(modelUsed, confidence) {
          confidenceRef.current = confidence;
          const result: AskResponse = {
            question,
            answer: answerRef.current,
            sources: sourcesRef.current,
            model_used: modelUsed,
            retrieval_used: retrievalRef.current,
            confidence,
          };
          setStreamingText(null);
          setResponse(result);
          void saveToHistory(result);
          setHistory(prev => [
            ...prev,
            { role: "user", content: question },
            { role: "assistant", content: answerRef.current },
          ].slice(-12) as ConversationTurn[]);
          setLoading(false);
        },
        onError(detail) {
          setError(detail);
          setStreamingText(null);
          setLoading(false);
        },
      }, {
        ...(sourceType ? { source_type_filter: sourceType } : {}),
        history: history.length > 0 ? history : undefined,
      }, signal);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return; // user cancelled
      setError(err instanceof Error ? err.message : "Wystąpił nieoczekiwany błąd.");
      setStreamingText(null);
      setLoading(false);
    }
  }, []);

  const handleSelectHistory = useCallback((question: string) => {
    setSidebarOpen(false);
    handleAsk(question);
  }, [handleAsk]);

  const handleNewConversation = useCallback(() => {
    setHistory([]);
    setResponse(null);
    setStreamingText(null);
    setError(null);
  }, []);

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
            {history.length > 0 && (
              <button
                onClick={handleNewConversation}
                className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800/60 transition-colors"
                title="Wyczyść historię rozmowy i zacznij nową"
              >
                <span>{Math.floor(history.length / 2)} wymian</span>
                <span>· Nowa rozmowa →</span>
              </button>
            )}
          </div>
          <div className="ml-auto flex items-center gap-3">
            <UsageBar />
            <div className="hidden sm:flex items-center gap-2 text-sm">
              <a href="/search" className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Szukaj</a>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <a href="/compare" className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Porównaj</a>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <a href="/history" className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Historia</a>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <a href="/admin" className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Admin</a>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <AlertsBadge />
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <a href="/account/api-tokens" className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">API</a>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <a href="/api/auth/signout" className="text-slate-500 dark:text-slate-400 hover:text-red-500 transition-colors">Wyloguj</a>
            </div>
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

          {/* Loading spinner — only before sources arrive */}
          {loading && streamingText === null && (
            <div className="mt-8 flex flex-col items-center gap-3 text-slate-500 dark:text-slate-400">
              <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
              <p className="text-sm">Przeszukuję akty prawne…</p>
            </div>
          )}

          {/* Streaming answer */}
          {streamingText !== null && (
            <div className="mt-6">
              <AnswerCard
                response={{
                  question: "",
                  answer: streamingText,
                  sources: sourcesRef.current,
                  model_used: "gpt-4o-mini",
                  retrieval_used: retrievalRef.current,
                }}
                streaming
              />
            </div>
          )}

          {/* Final answer */}
          {response && !loading && streamingText === null && (
            <div className="mt-6">
              <AnswerCard response={response} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
