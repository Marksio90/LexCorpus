"use client";

import { useState, FormEvent, Suspense } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";

type Mode = "login" | "register" | "email";

function LoginForm() {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [name,     setName]     = useState("");
  const [mode,     setMode]     = useState<Mode>("login");
  const [loading,  setLoading]  = useState(false);
  const [sent,     setSent]     = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") || "/ask";

  async function handleCredentials(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (mode === "register") {
      try {
        const res = await fetch("/api/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, name }),
        });
        const data = await res.json();
        if (!res.ok) {
          setError(data.error || "Błąd rejestracji");
          setLoading(false);
          return;
        }
        // Auto-login after registration
        const result = await signIn("credentials", {
          email,
          password,
          callbackUrl,
          redirect: true,
        });
        if (result?.error) {
          setError("Rejestracja udana, ale nie udało się zalogować.");
        }
      } catch {
        setError("Wystąpił nieoczekiwany błąd.");
      } finally {
        setLoading(false);
      }
      return;
    }

    // Login mode
    try {
      const result = await signIn("credentials", {
        email,
        password,
        callbackUrl,
        redirect: true,
      });
      if (result?.error) {
        setError("Nieprawidłowy email lub hasło.");
      }
    } catch {
      setError("Wystąpił nieoczekiwany błąd.");
    } finally {
      setLoading(false);
    }
  }

  async function handleEmail(e: FormEvent) {
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

  if (sent) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-8">
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
            onClick={() => { setSent(false); setEmail(""); setMode("email"); }}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            Użyj innego adresu
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-8">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1">
        {mode === "login" ? "Zaloguj się" : mode === "register" ? "Załóż konto" : "Zaloguj się e-mailem"}
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        {mode === "login"
          ? "Wpisz email i hasło, aby kontynuować."
          : mode === "register"
          ? "Utwórz nowe konto."
          : "Wyślemy Ci link — bez hasła."}
      </p>

      {mode === "email" ? (
        <form onSubmit={handleEmail} className="space-y-4">
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

          <div className="text-center">
            <button
              type="button"
              onClick={() => setMode("login")}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              Zaloguj się hasłem
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={handleCredentials} className="space-y-4">
          {mode === "register" && (
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                Imię (opcjonalnie)
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jan Kowalski"
                className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              />
            </div>
          )}

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

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Hasło
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "Min. 6 znaków" : "Twoje hasło"}
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
            disabled={loading || !email || !password}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl transition-colors"
          >
            {loading ? "Przetwarzanie…" : mode === "login" ? "Zaloguj się" : "Załóż konto"}
          </button>

          <div className="flex justify-between text-xs">
            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="text-blue-600 dark:text-blue-400 hover:underline"
            >
              {mode === "login" ? "Załóż konto" : "Masz już konto? Zaloguj się"}
            </button>
            <button
              type="button"
              onClick={() => { setMode("email"); setError(null); }}
              className="text-slate-500 dark:text-slate-400 hover:underline"
            >
              Zaloguj linkiem
            </button>
          </div>
        </form>
      )}

      <p className="mt-6 text-xs text-slate-400 dark:text-slate-500 text-center">
        Logując się, akceptujesz{" "}
        <a href="/regulamin" className="underline hover:text-slate-600">regulamin</a>{" "}
        i{" "}
        <a href="/polityka-prywatnosci" className="underline hover:text-slate-600">politykę prywatności</a>.
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <a href="/" className="inline-flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
            <span className="text-blue-600">Lex</span>Corpus
          </a>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            Polski AI do prawa — zaloguj się, żeby zadawać pytania
          </p>
        </div>

        <Suspense fallback={<div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-8 h-48 animate-pulse" />}>
          <LoginForm />
        </Suspense>

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
