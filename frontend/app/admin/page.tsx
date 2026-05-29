"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession, signIn, signOut } from "next-auth/react";
import { fetchHealth, fetchStats } from "@/lib/api";
import { AdminStats } from "@/components/AdminStats";
import type { HealthResponse, StatsResponse } from "@/lib/types";

export default function AdminPage() {
  const { data: session, status } = useSession();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, statsData] = await Promise.allSettled([fetchHealth(), fetchStats()]);
      if (healthData.status === "fulfilled") setHealth(healthData.value);
      else throw new Error((healthData.reason as Error).message);
      if (statsData.status === "fulfilled") setStats(statsData.value);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie można pobrać danych.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated") {
      refresh();
      const interval = setInterval(refresh, 30_000);
      return () => clearInterval(interval);
    }
  }, [status, refresh]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 px-4">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg p-8 w-full max-w-sm text-center">
          <span className="text-4xl">🔐</span>
          <h1 className="mt-4 text-xl font-bold text-slate-800 dark:text-slate-200">
            Panel administracyjny
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            Zaloguj się, aby uzyskać dostęp.
          </p>
          <button
            onClick={() => signIn("email")}
            className="mt-6 w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            Zaloguj się przez e-mail
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a
              href="/ask"
              className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
            >
              ← Wróć
            </a>
            <span className="text-slate-300 dark:text-slate-600">|</span>
            <h1 className="text-lg font-semibold">Panel administracyjny</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500 dark:text-slate-400 hidden sm:inline">
              {session?.user?.email}
            </span>
            <button
              onClick={() => signOut({ callbackUrl: "/ask" })}
              className="text-sm text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors"
            >
              Wyloguj
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Refresh control */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-800 dark:text-slate-200">
              Status systemu
            </h2>
            {lastRefresh && (
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Ostatnie odświeżenie: {lastRefresh.toLocaleTimeString("pl-PL")} · Auto-odświeżanie co 30s
              </p>
            )}
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
            Odśwież
          </button>
        </div>

        {error && (
          <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300 text-sm">
            {error}
          </div>
        )}

        {health ? (
          <AdminStats health={health} stats={stats} />
        ) : !error ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : null}
      </main>
    </div>
  );
}
