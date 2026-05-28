"use client";

import { useState, useRef, useCallback } from "react";

interface AskFormProps {
  onSubmit: (question: string) => void;
  loading: boolean;
}

const EXAMPLE_QUESTIONS = [
  "Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?",
  "Kiedy pracodawca może rozwiązać umowę bez wypowiedzenia?",
  "Jakie są zasady urlopu macierzyńskiego?",
];

export function AskForm({ onSubmit, loading }: AskFormProps) {
  const [question, setQuestion] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const q = question.trim();
      if (!q || loading) return;
      onSubmit(q);
    },
    [question, loading, onSubmit]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const q = question.trim();
        if (!q || loading) return;
        onSubmit(q);
      }
    },
    [question, loading, onSubmit]
  );

  const handleExample = (example: string) => {
    setQuestion(example);
    textareaRef.current?.focus();
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Zadaj pytanie prawne po polsku… (np. Jakie są prawa pracownika przy wypowiedzeniu?)"
          rows={4}
          disabled={loading}
          className="w-full px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none transition-colors disabled:opacity-60"
        />
        <div className="absolute bottom-3 right-3 text-xs text-slate-400 dark:text-slate-500">
          Ctrl+Enter
        </div>
      </div>

      {/* Example questions */}
      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => handleExample(ex)}
            disabled={loading}
            className="text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 hover:text-blue-700 dark:hover:text-blue-300 transition-colors disabled:opacity-50 truncate max-w-[200px]"
          >
            {ex.length > 40 ? ex.slice(0, 40) + "…" : ex}
          </button>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {question.length > 0 && `${question.length} / 2000 znaków`}
        </p>
        <button
          type="submit"
          disabled={!question.trim() || loading}
          className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors shadow-sm"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Szukam…
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Zapytaj
            </>
          )}
        </button>
      </div>
    </form>
  );
}
