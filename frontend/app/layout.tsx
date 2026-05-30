import type { Metadata } from "next";
import { SessionProvider } from "@/components/SessionProvider";
import "./globals.css";

const BASE_URL = process.env.NEXTAUTH_URL || "https://lexcorpus.pl";

export const metadata: Metadata = {
  metadataBase: new URL(BASE_URL),
  title: {
    default: "LexCorpus — Polski AI Prawny",
    template: "%s — LexCorpus",
  },
  description:
    "Odpowiedzi na pytania prawne z cytatami z ISAP, SAOS i EUR-Lex. AI przeszukuje 636 000 polskich dokumentów prawnych.",
  keywords: [
    "prawo polskie", "AI prawne", "akty prawne", "ISAP", "SAOS", "orzecznictwo",
    "asystent prawny", "LexCorpus", "pytania prawne", "kodeks pracy", "VAT",
  ],
  authors: [{ name: "LexCorpus" }],
  creator: "LexCorpus",
  openGraph: {
    type: "website",
    locale: "pl_PL",
    url: BASE_URL,
    siteName: "LexCorpus",
    title: "LexCorpus — Polski AI Prawny",
    description: "AI przeszukuje 636 000 polskich dokumentów prawnych i odpowiada z cytatami.",
  },
  twitter: {
    card: "summary",
    title: "LexCorpus — Polski AI Prawny",
    description: "AI przeszukuje 636 000 polskich dokumentów prawnych i odpowiada z cytatami.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  alternates: {
    canonical: BASE_URL,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 antialiased">
        <SessionProvider>
          {children}
        </SessionProvider>
      </body>
    </html>
  );
}
