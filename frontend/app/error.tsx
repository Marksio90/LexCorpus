"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[LexCorpus] Unhandled error:", error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-10 max-w-md text-center shadow-sm">
        <p className="text-4xl mb-4">⚠️</p>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">
          Coś poszło nie tak
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
          Wystąpił nieoczekiwany błąd. Spróbuj ponownie lub wróć do strony głównej.
          {error.digest && (
            <span className="block mt-2 font-mono text-xs text-slate-400">
              ID: {error.digest}
            </span>
          )}
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={reset}
            className="px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Spróbuj ponownie
          </button>
          <a
            href="/ask"
            className="px-4 py-2 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          >
            Strona główna
          </a>
        </div>
      </div>
    </div>
  );
}
