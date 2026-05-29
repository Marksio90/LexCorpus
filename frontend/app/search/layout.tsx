import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Wyszukiwarka dokumentów — LexCorpus",
  description: "Przeszukuj bazę ponad 636 000 dokumentów prawnych: ustaw, rozporządzeń i orzeczeń sądowych.",
  openGraph: {
    title:       "Wyszukiwarka dokumentów — LexCorpus",
    description: "Przeszukuj bazę ponad 636 000 dokumentów prawnych: ustaw, rozporządzeń i orzeczeń sądowych.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
