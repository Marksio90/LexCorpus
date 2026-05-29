"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function UpgradeSuccessPage() {
  const router = useRouter();

  // Odśwież sesję żeby tier się zaktualizował
  useEffect(() => {
    const t = setTimeout(() => router.push("/ask"), 4000);
    return () => clearTimeout(t);
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <div className="w-20 h-20 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
          <svg className="w-10 h-10 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Dziękujemy!</h1>
        <p className="text-slate-500 dark:text-slate-400 mb-6">
          Twój plan został aktywowany. Za chwilę zostaniesz przekierowany do aplikacji.
        </p>
        <a
          href="/ask"
          className="inline-block px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
        >
          Przejdź do LexCorpus →
        </a>
      </div>
    </div>
  );
}
