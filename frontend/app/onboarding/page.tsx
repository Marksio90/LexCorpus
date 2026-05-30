"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

const STEPS = [
  {
    icon: "⚖️",
    title: "Witaj w LexCorpus",
    description:
      "Jesteś połączony z bazą 636 000 polskich dokumentów prawnych — ustaw i orzecznictwa.",
    hint: 'Zadaj pytanie po polsku, np. „Jakie są prawa pracownika przy zwolnieniu?”',
  },
  {
    icon: "🔍",
    title: "Jak działa wyszukiwanie?",
    description:
      "Systm używa hybrydowego wyszukiwania: gęste embeddingi + BM25 + cross-encoder reranking. " +
      "Każda odpowiedź zawiera cytaty z konkretnych aktów prawnych.",
    hint: "Filtry źródeł (legislacja, NSA, SN, TK) pozwalają zawęzić wyniki.",
  },
  {
    icon: "🔔",
    title: "Alerty zmian w prawie",
    description:
      "Gdy prawo związane z Twoimi pytaniami się zmieni — dostaniesz powiadomienie. " +
      "Co tydzień wysyłamy digest nowych orzeczeń i nowelizacji.",
    hint: "Alerty włączysz w zakładce /alerts. Newsletter — w ustawieniach konta.",
  },
  {
    icon: "📄",
    title: "Prywatne dokumenty",
    description:
      "W planie Pro i Kancelaria możesz wgrać własne umowy lub pisma. " +
      "System będzie odpowiadać na pytania zarówno z bazy publicznej, jak i Twoich dokumentów.",
    hint: "Prywatne dokumenty są dostępne tylko dla Ciebie.",
  },
];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const router = useRouter();
  const { data: session } = useSession();
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  // On mount: check if this user already completed onboarding (backfills cookie too).
  // If done, skip straight to /ask.
  useState(() => {
    fetch("/api/onboarding/sync")
      .then((r) => r.json())
      .then(({ done }) => { if (done) router.replace("/ask"); })
      .catch(() => {});
  });

  async function finish() {
    await fetch("/api/onboarding", { method: "POST" }).catch(() => {});
    router.push("/ask");
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-950 flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-10">
          <span className="text-3xl font-bold text-white">
            <span className="text-blue-400">Lex</span>Corpus
          </span>
        </div>

        {/* Card */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl overflow-hidden">
          {/* Progress bar */}
          <div className="h-1 bg-slate-200 dark:bg-slate-700">
            <div
              className="h-1 bg-blue-500 transition-all duration-500"
              style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            />
          </div>

          <div className="p-8">
            {/* Icon */}
            <div className="text-5xl mb-4 text-center">{current.icon}</div>

            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 text-center mb-3">
              {current.title}
            </h2>
            <p className="text-slate-600 dark:text-slate-300 text-center text-sm leading-relaxed mb-6">
              {current.description}
            </p>

            {/* Hint box */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl px-4 py-3 mb-8">
              <p className="text-xs text-blue-700 dark:text-blue-300 text-center">
                💡 {current.hint}
              </p>
            </div>

            {/* Steps indicator */}
            <div className="flex justify-center gap-2 mb-8">
              {STEPS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setStep(i)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    i === step
                      ? "bg-blue-600 w-6"
                      : i < step
                      ? "bg-blue-300"
                      : "bg-slate-300 dark:bg-slate-600"
                  }`}
                />
              ))}
            </div>

            {/* Buttons */}
            <div className="flex gap-3">
              {step > 0 && (
                <button
                  onClick={() => setStep((s) => s - 1)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                >
                  Wstecz
                </button>
              )}
              <button
                onClick={isLast ? finish : () => setStep((s) => s + 1)}
                className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
              >
                {isLast ? "Zacznij zadawać pytania →" : "Dalej"}
              </button>
            </div>

            {/* Skip */}
            {!isLast && (
              <button
                onClick={finish}
                className="w-full mt-3 text-xs text-slate-400 hover:text-slate-600 transition-colors text-center"
              >
                Pomiń intro
              </button>
            )}
          </div>
        </div>

        {session?.user?.email && (
          <p className="text-center text-xs text-slate-400 mt-4">
            Zalogowany jako {session.user.email}
          </p>
        )}
      </div>
    </div>
  );
}
