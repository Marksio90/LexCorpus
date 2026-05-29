import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Twoje statystyki — LexCorpus",
  description: "Twoje statystyki użycia LexCorpus: aktywność, źródła, alerty.",
  openGraph: {
    title:       "Twoje statystyki — LexCorpus",
    description: "Twoje statystyki użycia LexCorpus: aktywność, źródła, alerty.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
