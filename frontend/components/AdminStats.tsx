"use client";

import type { HealthResponse } from "@/lib/types";

interface AdminStatsProps {
  health: HealthResponse;
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div
      className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${
        ok
          ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300"
          : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300"
      }`}
    >
      <div
        className={`w-2.5 h-2.5 rounded-full ${ok ? "bg-green-500" : "bg-red-500"} animate-pulse`}
      />
      <span className="text-sm font-medium">{label}</span>
      <span className="ml-auto text-xs font-semibold">
        {ok ? "OK" : "BŁĄD"}
      </span>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number | null;
  icon: React.ReactNode;
}) {
  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wide">{label}</p>
          <p className="mt-1 text-2xl font-bold text-slate-800 dark:text-slate-200">
            {value !== null && value !== undefined ? value.toString() : "—"}
          </p>
        </div>
        <div className="text-2xl">{icon}</div>
      </div>
    </div>
  );
}

export function AdminStats({ health }: AdminStatsProps) {
  const overallOk =
    health.status === "ok" &&
    health.qdrant_connected &&
    health.embedding_model_loaded;

  return (
    <div className="space-y-6">
      {/* Overall status */}
      <div
        className={`flex items-center gap-3 p-4 rounded-xl border-2 ${
          overallOk
            ? "bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700"
            : "bg-orange-50 dark:bg-orange-900/20 border-orange-300 dark:border-orange-700"
        }`}
      >
        <span className="text-2xl">{overallOk ? "✅" : "⚠️"}</span>
        <div>
          <p className="font-semibold text-slate-800 dark:text-slate-200">
            {overallOk ? "System działa poprawnie" : "System działa z ograniczeniami"}
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Status API: <span className="font-mono">{health.status}</span>
          </p>
        </div>
      </div>

      {/* Service statuses */}
      <div>
        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-3">
          Usługi
        </h3>
        <div className="space-y-2">
          <StatusBadge ok={health.qdrant_connected} label="Qdrant (baza wektorów)" />
          <StatusBadge ok={health.embedding_model_loaded} label="Model embeddingów" />
          <StatusBadge ok={health.model_loaded} label="Lokalny model językowy" />
        </div>
      </div>

      {/* Stats cards */}
      <div>
        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-3">
          Statystyki
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Wektory w Qdrant"
            value={health.collection_count?.toLocaleString("pl-PL") ?? null}
            icon="📊"
          />
          <StatCard
            label="Model lokalny"
            value={health.model_loaded ? "Załadowany" : "Niedostępny"}
            icon="🤖"
          />
          <StatCard
            label="Model embeddingów"
            value={health.embedding_model_loaded ? "Aktywny" : "Niedostępny"}
            icon="🔍"
          />
        </div>
      </div>

      {/* Raw JSON */}
      <div>
        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-3">
          Surowe dane health check
        </h3>
        <pre className="bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 rounded-xl p-4 text-xs font-mono overflow-x-auto border border-slate-200 dark:border-slate-700">
          {JSON.stringify(health, null, 2)}
        </pre>
      </div>
    </div>
  );
}
