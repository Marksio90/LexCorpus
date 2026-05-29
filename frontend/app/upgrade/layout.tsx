import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Plany i cennik — LexCorpus",
  description: "Wybierz plan LexCorpus: Free, Pro lub Kancelaria.",
  openGraph: {
    title:       "Plany i cennik — LexCorpus",
    description: "Wybierz plan LexCorpus: Free, Pro lub Kancelaria.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
