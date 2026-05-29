import type { Metadata } from "next";

export const metadata: Metadata = {
  title:       "Historia pytań — LexCorpus",
  description: "Historia Twoich pytań prawnych w LexCorpus.",
  openGraph: {
    title:       "Historia pytań — LexCorpus",
    description: "Historia Twoich pytań prawnych w LexCorpus.",
    siteName:    "LexCorpus",
    locale:      "pl_PL",
    type:        "website",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
