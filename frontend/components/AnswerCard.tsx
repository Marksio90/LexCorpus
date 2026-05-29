"use client";

import { useState } from "react";
import type { AskResponse, SourceDocument } from "@/lib/types";
import { SourceList, SourceTypeBadge, buildExternalLink } from "./SourceList";
import { PdfDownloadButton } from "./PdfDownloadButton";

interface AnswerCardProps {
  response: AskResponse;
  streaming?: boolean;
}

// ── Export helpers ────────────────────────────────────────────────────────────

function buildMarkdown(response: AskResponse): string {
  const { question, answer, sources, model_used } = response;
  const lines: string[] = [];

  lines.push(`# Pytanie prawne`);
  lines.push(``);
  lines.push(`**${question}**`);
  lines.push(``);
  lines.push(`---`);
  lines.push(``);
  lines.push(`## Odpowiedź`);
  lines.push(``);
  lines.push(answer);
  lines.push(``);

  if (sources.length > 0) {
    lines.push(`---`);
    lines.push(``);
    lines.push(`## Źródła prawne`);
    lines.push(``);
    sources.forEach((s, i) => {
      const link = buildExternalLink(s);
      const url = link ? ` — [${link.label}](${link.url})` : "";
      lines.push(`**[${i + 1}]** ${s.title || s.act_id} (${s.year})${url}`);
      if (s.citation) lines.push(`> ${s.citation}`);
      lines.push(``);
    });
  }

  lines.push(`---`);
  lines.push(`*Wygenerowano przez LexCorpus · Model: ${model_used} · ${new Date().toLocaleDateString("pl-PL")}*`);

  return lines.join("\n");
}

function buildPlainText(response: AskResponse): string {
  const { question, answer, sources, model_used } = response;
  const lines: string[] = [];

  lines.push(`PYTANIE:`);
  lines.push(question);
  lines.push(``);
  lines.push(`ODPOWIEDŹ:`);
  lines.push(answer);
  lines.push(``);

  if (sources.length > 0) {
    lines.push(`ŹRÓDŁA PRAWNE:`);
    sources.forEach((s, i) => {
      const link = buildExternalLink(s);
      lines.push(`[${i + 1}] ${s.title || s.act_id} (${s.year})`);
      if (s.citation) lines.push(`    ${s.citation}`);
      if (link) lines.push(`    ${link.url}`);
    });
    lines.push(``);
  }

  lines.push(`Wygenerowano przez LexCorpus · Model: ${model_used} · ${new Date().toLocaleDateString("pl-PL")}`);
  return lines.join("\n");
}

function CopyButton({ response }: { response: AskResponse }) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildPlainText(response));
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
        state === "copied"
          ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
          : state === "error"
          ? "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300"
          : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
      }`}
      title="Kopiuj odpowiedź do schowka"
    >
      {state === "copied" ? (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Skopiowano
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Kopiuj
        </>
      )}
    </button>
  );
}

function DownloadButton({ response }: { response: AskResponse }) {
  const handleDownload = () => {
    const md = buildMarkdown(response);
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const slug = response.question.slice(0, 40).replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ\s]/g, "").trim().replace(/\s+/g, "_");
    a.download = `lexcorpus_${slug}_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button
      onClick={handleDownload}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
      title="Pobierz jako plik Markdown"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      Pobierz .md
    </button>
  );
}

// ── Citation tooltip ──────────────────────────────────────────────────────────

function CitationTooltip({ source, num }: { source: SourceDocument; num: number }) {
  const externalLink = buildExternalLink(source);
  return (
    <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl shadow-xl p-3 text-left pointer-events-auto">
      <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-slate-200 dark:border-t-slate-600" />
      <div className="flex items-start gap-2 mb-2">
        <span className="flex-shrink-0 w-5 h-5 rounded bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-bold flex items-center justify-center">
          {num}
        </span>
        <SourceTypeBadge type={source.source_type ?? "unknown"} />
      </div>
      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-snug mb-1 line-clamp-2">
        {source.title || source.act_id}
      </p>
      {(source.year || source.pos) && (
        <p className="text-xs text-slate-400 dark:text-slate-500 mb-2">
          {[source.year, source.pos ? `poz. ${source.pos}` : ""].filter(Boolean).join(" · ")}
        </p>
      )}
      <div className="flex items-center gap-2">
        <button
          onClick={() => document.getElementById(`source-${num}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
          className="text-xs text-slate-600 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
        >
          ↓ Przejdź do źródła
        </button>
        {externalLink && (
          <a
            href={externalLink.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
          >
            {externalLink.label}
          </a>
        )}
      </div>
    </div>
  );
}

function CitationBadge({ num, source }: { num: number; source: SourceDocument }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-flex align-middle">
      <button
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => document.getElementById(`source-${num}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
        className="inline-flex items-center justify-center w-5 h-5 mx-0.5 rounded text-xs font-bold bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors cursor-pointer"
        aria-label={`Źródło ${num}: ${source.title}`}
      >
        {num}
      </button>
      {open && <CitationTooltip source={source} num={num} />}
    </span>
  );
}

function AnswerText({ text, sources }: { text: string; sources: SourceDocument[] }) {
  if (sources.length === 0) {
    return (
      <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-sm whitespace-pre-wrap">
        {text}
      </p>
    );
  }

  const parts = text.split(/(\[\d+\])/g);

  return (
    <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-sm whitespace-pre-wrap">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (!match) return part;
        const num = parseInt(match[1], 10);
        const source = sources[num - 1];
        if (!source) return part;
        return <CitationBadge key={i} num={num} source={source} />;
      })}
    </p>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function AnswerCard({ response, streaming = false }: AnswerCardProps) {
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
        <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
            Odpowiedź
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
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
            {!streaming && (
              <>
                <CopyButton response={response} />
                <DownloadButton response={response} />
                <PdfDownloadButton response={response} />
              </>
            )}
          </div>
        </div>

        <AnswerText text={answer} sources={sources} />
        {streaming && (
          <span className="inline-block w-0.5 h-4 ml-0.5 bg-slate-500 dark:bg-slate-400 animate-pulse align-middle" />
        )}
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
