import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Historia zmian aktów — LexCorpus",
  description: "Przeglądaj historię wykrytych zmian w aktach prawnych i orzeczeniach.",
  openGraph: {
    title:       "Historia zmian aktów — LexCorpus",
    description: "Przeglądaj historię wykrytych zmian w aktach prawnych i orzeczeniach.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
