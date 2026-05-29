import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Wyszukiwarka precedensów — LexCorpus",
  description: "Opisz stan faktyczny i znajdź najbardziej trafne orzeczenia sądów polskich.",
  openGraph: {
    title:       "Wyszukiwarka precedensów — LexCorpus",
    description: "Opisz stan faktyczny i znajdź najbardziej trafne orzeczenia sądów polskich.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
