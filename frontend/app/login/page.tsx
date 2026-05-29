"use client";

import { useState, FormEvent } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";

export default function LoginPage() {
  const [email,   setEmail]   = useState("");
  const [loading, setLoading] = useState(false);
  const [sent,    setSent]    = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") || "/ask";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await signIn("email", { email, callbackUrl, redirect: false });
      if (result?.error) {
        setError("Błąd wysyłania e-maila. Sprawdź adres i spróbuj ponownie.");
      } else {
        setSent(true);
      }
    } catch {
      setError("Wystąpił nieoczekiwany błąd. Spróbuj ponownie.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo / brand */}
        <div className="text-center mb-8">
          <a href="/" className="inline-flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
            <span className="text-blue-600">Lex</span>Corpus
          </a>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            Polski AI do prawa — zaloguj się, żeby zadawać pytania
          </p>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-8">
          {sent ? (
            <div className="text-center space-y-4">
              <div className="w-14 h-14 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto">
                <svg className="w-7 h-7 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-slate-900 dark:text-slate-100">Sprawdź skrzynkę</p>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  Wysłaliśmy link do logowania na <strong>{email}</strong>.<br />
                  Link wygaśnie za 24 godziny.
                </p>
              </div>
              <button
                onClick={() => { setSent(false); setEmail(""); }}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                Użyj innego adresu
              </button>
            </div>
          ) : (
            <>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1">
                Zaloguj się
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                Wyślemy Ci link — bez hasła, bez rejestracji.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Adres e-mail
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="jan@kancelaria.pl"
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  />
                </div>

                {error && (
                  <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={loading || !email}
                  className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl transition-colors"
                >
                  {loading ? "Wysyłanie…" : "Wyślij link do logowania"}
                </button>
              </form>

              <p className="mt-6 text-xs text-slate-400 dark:text-slate-500 text-center">
                Logując się, akceptujesz{" "}
                <a href="#" className="underline hover:text-slate-600">regulamin</a>{" "}
                i{" "}
                <a href="#" className="underline hover:text-slate-600">politykę prywatności</a>.
              </p>
            </>
          )}
        </div>

        {/* Tier info */}
        <div className="mt-6 grid grid-cols-3 gap-3 text-center text-xs text-slate-500 dark:text-slate-400">
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 py-3 px-2">
            <p className="font-semibold text-slate-700 dark:text-slate-300">Free</p>
            <p>20 pytań/dzień</p>
          </div>
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-200 dark:border-blue-800 py-3 px-2">
            <p className="font-semibold text-blue-700 dark:text-blue-300">Pro</p>
            <p>500 pytań/dzień</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 py-3 px-2">
            <p className="font-semibold text-slate-700 dark:text-slate-300">Kancelaria</p>
            <p>Nieograniczone</p>
          </div>
        </div>
      </div>
    </div>
  );
}
