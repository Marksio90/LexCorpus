import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Kreator dokumentów prawnych — LexCorpus",
  description: "Generuj profesjonalne dokumenty prawne: umowy, pisma, pełnomocnictwa — w kilka sekund.",
  openGraph: {
    title:       "Kreator dokumentów prawnych — LexCorpus",
    description: "Generuj profesjonalne dokumenty prawne: umowy, pisma, pełnomocnictwa — w kilka sekund.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
