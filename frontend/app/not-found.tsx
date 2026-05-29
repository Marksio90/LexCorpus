import type { Metadata } from "next";

export const metadata: Metadata = { title: "Nie znaleziono — LexCorpus" };

export default function NotFound() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-10 max-w-md text-center shadow-sm">
        <p className="text-5xl font-black text-slate-200 dark:text-slate-700 mb-4">404</p>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">
          Strona nie istnieje
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
          Podany adres nie istnieje lub link jest nieaktualny.
        </p>
        <a
          href="/ask"
          className="inline-block px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          ← Wróć do LexCorpus
        </a>
      </div>
    </div>
  );
}
