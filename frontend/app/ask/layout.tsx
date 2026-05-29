import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Asystent prawny — LexCorpus",
  description: "Zadaj pytanie prawne i uzyskaj odpowiedź opartą na polskim ustawodawstwie i orzecznictwie.",
  openGraph: {
    title:       "Asystent prawny — LexCorpus",
    description: "Zadaj pytanie prawne i uzyskaj odpowiedź opartą na polskim ustawodawstwie i orzecznictwie.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
