import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Zapytaj eksperta — LexCorpus",
  description: "Zadaj pytanie licencjonowanemu prawnikowi i uzyskaj profesjonalną odpowiedź.",
  openGraph: {
    title:       "Zapytaj eksperta — LexCorpus",
    description: "Zadaj pytanie licencjonowanemu prawnikowi i uzyskaj profesjonalną odpowiedź.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
