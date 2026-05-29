import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Analiza dokumentu — LexCorpus",
  description: "Prześlij umowę lub pismo i uzyskaj analizę AI: ryzyka, klauzule abuzywne, rekomendację.",
  openGraph: {
    title:       "Analiza dokumentu — LexCorpus",
    description: "Prześlij umowę lub pismo i uzyskaj analizę AI: ryzyka, klauzule abuzywne, rekomendację.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
