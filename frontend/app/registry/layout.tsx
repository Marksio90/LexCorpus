import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Monitoring rejestru — LexCorpus",
  description: "Subskrybuj konkretne akty prawne i otrzymuj natychmiastowe powiadomienia o zmianach.",
  openGraph: {
    title:       "Monitoring rejestru — LexCorpus",
    description: "Subskrybuj konkretne akty prawne i otrzymuj natychmiastowe powiadomienia o zmianach.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
