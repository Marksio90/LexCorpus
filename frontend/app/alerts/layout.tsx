import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Alerty prawne — LexCorpus",
  description: "Alerty o zmianach w prawie powiązanych z Twoimi pytaniami.",
  openGraph: {
    title:       "Alerty prawne — LexCorpus",
    description: "Alerty o zmianach w prawie powiązanych z Twoimi pytaniami.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
