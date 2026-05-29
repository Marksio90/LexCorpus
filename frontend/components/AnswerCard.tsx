"use client";

import { useRef } from "react";
import type { AskResponse } from "@/lib/types";
import { SourceList } from "./SourceList";

interface AnswerCardProps {
  response: AskResponse;
}

/** Replace [1], [2] etc. in answer text with clickable anchor links. */
function AnswerText({ text, sourceCount }: { text: string; sourceCount: number }) {
  if (sourceCount === 0) {
    return <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-sm whitespace-pre-wrap">{text}</p>;
  }

  // Split on citation markers like [1], [2], ..., [99]
  const parts = text.split(/(\[\d+\])/g);

  return (
    <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-sm whitespace-pre-wrap">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (!match) return part;
        const num = parseInt(match[1], 10);
        if (num < 1 || num > sourceCount) return part;
        return (
          <a
            key={i}
            href={`#source-${num}`}
            onClick={(e) => {
              e.preventDefault();
              document.getElementById(`source-${num}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
            className="inline-flex items-center justify-center w-5 h-5 mx-0.5 rounded text-xs font-bold bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors cursor-pointer align-middle"
            title={`Przejdź do źródła ${num}`}
          >
            {num}
          </a>
        );
      })}
    </p>
  );
}

export function AnswerCard({ response }: AnswerCardProps) {
  const { answer, model_used, retrieval_used, sources, question } = response;

  return (
    <div className="space-y-4">
      {/* Question echo */}
      <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl">
        <p className="text-xs text-blue-500 dark:text-blue-400 font-semibold uppercase tracking-wide mb-1">
          Pytanie
        </p>
        <p className="text-slate-800 dark:text-slate-200">{question}</p>
      </div>

      {/* Answer */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
            Odpowiedź
          </h2>
          <div className="flex items-center gap-2">
            {retrieval_used && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
                RAG
              </span>
            )}
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-mono">
              {model_used}
            </span>
          </div>
        </div>

        <AnswerText text={answer} sourceCount={sources.length} />
      </div>

      {/* Sources */}
      {sources.length > 0 && (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-3">
            Źródła prawne ({sources.length})
          </h2>
          <SourceList sources={sources} />
        </div>
      )}
    </div>
  );
}
