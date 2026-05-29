"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const PDFDownloadLink = dynamic(
  () => import("@react-pdf/renderer").then((m) => m.PDFDownloadLink),
  { ssr: false },
);

const DraftDocument = dynamic(
  () => import("./DraftDocument"),
  { ssr: false },
);

interface Props {
  text:     string;
  filename: string;
}

export default function DraftPdfButton({ text, filename }: Props) {
  const [rendered, setRendered] = useState(false);

  if (!rendered) {
    return (
      <button
        onClick={() => setRendered(true)}
        className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 transition-colors px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20"
      >
        Pobierz PDF
      </button>
    );
  }

  return (
    <PDFDownloadLink
      document={<DraftDocument text={text} title={filename} />}
      fileName={`${filename.replace(/\s+/g, "_")}.pdf`}
    >
      {({ loading }) =>
        loading ? (
          <span className="text-xs text-slate-400 px-2 py-1">Generowanie…</span>
        ) : (
          <span className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 cursor-pointer px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20">
            ⬇ Pobierz PDF
          </span>
        )
      }
    </PDFDownloadLink>
  );
}
