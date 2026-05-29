"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { AskResponse } from "@/lib/types";

// @react-pdf/renderer używa API przeglądarki — ładujemy tylko client-side
const PDFDownloadLink = dynamic(
  () => import("@react-pdf/renderer").then((m) => m.PDFDownloadLink),
  { ssr: false }
);
const LegalReportDocumentDynamic = dynamic(
  () => import("./LegalReportDocument").then((m) => m.LegalReportDocument),
  { ssr: false }
);

interface Props {
  response: AskResponse;
}

export function PdfDownloadButton({ response }: Props) {
  const [rendered, setRendered] = useState(false);
  const createdAt = new Date().toISOString();

  const slug = response.question
    .slice(0, 40)
    .replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ\s]/g, "")
    .trim()
    .replace(/\s+/g, "_");
  const filename = `lexcorpus_${slug}_${createdAt.slice(0, 10)}.pdf`;

  // Lazy — render dopiero po kliknięciu "Przygotuj PDF"
  if (!rendered) {
    return (
      <button
        onClick={() => setRendered(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors border border-red-200 dark:border-red-800"
        title="Wygeneruj raport PDF z cytowaniami"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        Pobierz PDF
      </button>
    );
  }

  return (
    <PDFDownloadLink
      document={
        <LegalReportDocumentDynamic
          response={response}
          createdAt={createdAt}
        />
      }
      fileName={filename}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border"
      style={{}}
    >
      {({ loading }: { loading: boolean }) =>
        loading ? (
          <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700">
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            Generowanie…
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 border-red-200 dark:border-red-800 px-3 py-1.5 rounded-lg">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Pobierz PDF ↓
          </span>
        )
      }
    </PDFDownloadLink>
  );
}
