import Link from "next/link";

const EXAMPLE_QUESTIONS = [
  "Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?",
  "Kiedy przedawniają się zobowiązania podatkowe?",
  "Jakie wymogi musi spełniać umowa o dzieło?",
  "Co to jest rękojmia i jak długo trwa?",
  "Czy pracodawca może zmienić warunki pracy bez zgody pracownika?",
  "Jakie są przesłanki ogłoszenia upadłości konsumenckiej?",
];

const FEATURES = [
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    title: "636 000 dokumentów",
    description: "Akty prawne z ISAP i orzeczenia sądów (NSA, SN, TK, sądy powszechne) — dane, których duże modele nie mają w pełni zaindeksowanych.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: "Hybrid RAG",
    description: "Dense embeddings + BM25 sparse search + RRF fusion + cross-encoder reranking + query expansion. Nie zwykłe wyszukiwanie słów kluczowych.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
      </svg>
    ),
    title: "Cytowane źródła",
    description: "Każda odpowiedź powołuje się na konkretne artykuły i orzeczenia z bezpośrednimi linkami do ISAP i SAOS.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
    title: "Aktualne dane",
    description: "Automatyczny tygodniowy sync nowych orzeczeń z SAOS. Baza rośnie o ~2000 wyroków tygodniowo.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: "Tryb porównawczy",
    description: "Zadaj jedno pytanie i porównaj odpowiedzi z ustaw vs orzecznictwa NSA/SN/TK obok siebie.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
    title: "Open source",
    description: "Pełny kod dostępny na GitHubie. Możesz wdrożyć własną instancję na własnym serwerze.",
  },
];

const SOURCE_TYPES = [
  { label: "Ustawy ISAP",    count: "~4 000/rok",   color: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300" },
  { label: "NSA / WSA",      count: "~80 000/rok",  color: "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300" },
  { label: "Sąd Najwyższy",  count: "~10 000/rok",  color: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300" },
  { label: "Trybunał Konst.", count: "~300/rok",     color: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300" },
  { label: "Sądy powszechne", count: "~5 000/rok",  color: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-slate-900">
      {/* Nav */}
      <nav className="border-b border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xl">⚖️</span>
            <span className="text-lg font-bold text-slate-900 dark:text-slate-100">LexCorpus</span>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/search" className="hidden sm:inline text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 transition-colors px-3 py-1.5">
              Szukaj
            </Link>
            <Link href="/ask" className="text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg transition-colors">
              Zadaj pytanie →
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 py-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          Polski AI Prawny · 636 000 dokumentów
        </div>

        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-slate-900 dark:text-slate-100 leading-tight mb-6">
          Zapytaj o polskie prawo.{" "}
          <span className="text-blue-600 dark:text-blue-400">Dostań odpowiedź</span>{" "}
          z cytowanymi przepisami.
        </h1>

        <p className="text-lg text-slate-500 dark:text-slate-400 max-w-2xl mx-auto mb-10">
          LexCorpus przeszukuje akty prawne z ISAP i orzeczenia sądów,
          a następnie generuje odpowiedź z konkretnymi artykułami i linkami do źródeł.
          Nie halucynuje — cytuje tylko to, co znalazł.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center mb-16">
          <Link
            href="/ask"
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl transition-colors text-sm"
          >
            Zadaj pytanie prawne →
          </Link>
          <Link
            href="/search"
            className="px-6 py-3 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 font-semibold rounded-xl transition-colors text-sm"
          >
            Szukaj dokumentów
          </Link>
        </div>

        {/* Example questions */}
        <div className="text-left max-w-2xl mx-auto">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3 text-center">
            Przykładowe pytania
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <Link
                key={q}
                href={`/ask?q=${encodeURIComponent(q)}`}
                className="flex items-start gap-2 p-3 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-sm text-slate-700 dark:text-slate-300 group"
              >
                <svg className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {q}
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Sources strip */}
      <section className="bg-slate-50 dark:bg-slate-800/50 border-y border-slate-100 dark:border-slate-800 py-8">
        <div className="max-w-6xl mx-auto px-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide text-center mb-4">
            Źródła danych
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {SOURCE_TYPES.map(({ label, count, color }) => (
              <div key={label} className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${color}`}>
                <span>{label}</span>
                <span className="opacity-60">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features grid */}
      <section className="max-w-6xl mx-auto px-4 py-20">
        <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 text-center mb-3">
          Jak to działa?
        </h2>
        <p className="text-slate-500 dark:text-slate-400 text-center mb-12 max-w-xl mx-auto">
          Nie kolejny wrapper na ChatGPT. Własny pipeline retrieval z danych, których duże modele nie mają.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(({ icon, title, description }) => (
            <div key={title} className="p-6 rounded-2xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-800/50 hover:border-blue-200 dark:hover:border-blue-800 transition-colors">
              <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center mb-4">
                {icon}
              </div>
              <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-2">{title}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline diagram */}
      <section className="bg-slate-50 dark:bg-slate-800/50 border-y border-slate-100 dark:border-slate-800 py-16">
        <div className="max-w-4xl mx-auto px-4">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 text-center mb-10">
            Pipeline RAG
          </h2>
          <div className="flex flex-wrap justify-center items-center gap-2 text-sm">
            {[
              { label: "Pytanie", sub: "dowolny język" },
              null,
              { label: "Query expansion", sub: "GPT-4o-mini × 3" },
              null,
              { label: "Hybrid search", sub: "dense + BM25 + RRF" },
              null,
              { label: "Cross-encoder", sub: "reranking" },
              null,
              { label: "Odpowiedź", sub: "z cytowaniami [N]" },
            ].map((item, i) =>
              item === null ? (
                <svg key={i} className="w-5 h-5 text-slate-300 dark:text-slate-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              ) : (
                <div key={item.label} className="flex flex-col items-center px-4 py-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm">
                  <span className="font-medium text-slate-800 dark:text-slate-200">{item.label}</span>
                  <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{item.sub}</span>
                </div>
              )
            )}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-4 py-20 text-center">
        <h2 className="text-3xl font-bold text-slate-900 dark:text-slate-100 mb-4">
          Gotowy? Zadaj pierwsze pytanie.
        </h2>
        <p className="text-slate-500 dark:text-slate-400 mb-8 max-w-lg mx-auto">
          Bezpłatnie. Bez rejestracji. Odpowiedź w kilka sekund.
        </p>
        <Link
          href="/ask"
          className="inline-flex items-center gap-2 px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-2xl transition-colors text-base shadow-lg shadow-blue-600/20"
        >
          Zadaj pytanie prawne
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
          </svg>
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-100 dark:border-slate-800 py-8">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-slate-400 dark:text-slate-500">
          <div className="flex items-center gap-2">
            <span>⚖️</span>
            <span>LexCorpus — Polski AI Prawny</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/ask"     className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors">Pytaj AI</Link>
            <Link href="/search"  className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors">Szukaj</Link>
            <Link href="/compare" className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors">Porównaj</Link>
            <Link href="/history" className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors">Historia</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
