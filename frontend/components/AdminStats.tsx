"use client";

import type { HealthResponse, StatsResponse, SourceBreakdown } from "@/lib/types";

interface AdminStatsProps {
  health: HealthResponse;
  stats: StatsResponse | null;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${
        ok ? "bg-green-500" : "bg-red-500"
      } animate-pulse`}
    />
  );
}

function StatusRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-100 dark:border-slate-700 last:border-0">
      <div className="flex items-center gap-2.5">
        <StatusDot ok={ok} />
        <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
      </div>
      <span
        className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
          ok
            ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
            : "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300"
        }`}
      >
        {ok ? "OK" : "BŁĄD"}
      </span>
    </div>
  );
}

const SOURCE_META: {
  key: keyof Omit<SourceBreakdown, "total">;
  label: string;
  bar: string;
  badge: string;
}[] = [
  { key: "legislation",     label: "Ustawy (ISAP)",         bar: "bg-blue-500",   badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  { key: "judgment_nsa",    label: "NSA / WSA",              bar: "bg-purple-500", badge: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300" },
  { key: "judgment_sn",     label: "Sąd Najwyższy",          bar: "bg-indigo-500", badge: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300" },
  { key: "judgment_tk",     label: "Trybunał Konstytucyjny", bar: "bg-red-500",    badge: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
  { key: "judgment_common", label: "Sądy powszechne",        bar: "bg-slate-500",  badge: "bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300" },
  { key: "judgment_kio",    label: "KIO",                    bar: "bg-orange-500", badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300" },
];

function SourceBreakdownChart({ breakdown }: { breakdown: SourceBreakdown }) {
  const total = breakdown.total || 1;

  return (
    <div className="space-y-3">
      {SOURCE_META.map(({ key, label, bar, badge }) => {
        const count = breakdown[key] ?? 0;
        const pct = Math.round((count / total) * 100);
        return (
          <div key={key}>
            <div className="flex items-center justify-between mb-1">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badge}`}>
                {label}
              </span>
              <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span className="font-mono font-semibold text-slate-700 dark:text-slate-300">
                  {count.toLocaleString("pl-PL")}
                </span>
                <span className="w-8 text-right">{pct}%</span>
              </div>
            </div>
            <div className="w-full h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full ${bar} rounded-full transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ConfigPill({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`text-xs px-3 py-1 rounded-full font-medium ${
        active
          ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
          : "bg-slate-100 text-slate-400 dark:bg-slate-700 dark:text-slate-500 line-through"
      }`}
    >
      {label}
    </span>
  );
}

export function AdminStats({ health, stats }: AdminStatsProps) {
  const overallOk =
    health.status === "ok" && health.qdrant_connected && health.embedding_model_loaded;

  return (
    <div className="space-y-6">
      {/* Overall banner */}
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Services */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">
            Usługi
          </h3>
          <StatusRow ok={health.qdrant_connected} label="Qdrant (baza wektorów)" />
          <StatusRow ok={health.embedding_model_loaded} label="Model embeddingów" />
          <StatusRow ok={health.model_loaded} label="Lokalny model LLM" />
        </div>

        {/* Config */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">
            Konfiguracja RAG
          </h3>
          {stats ? (
            <div className="space-y-3">
              <div>
                <p className="text-xs text-slate-400 mb-1">Model embeddingów</p>
                <p className="text-sm font-mono text-slate-700 dark:text-slate-300 truncate">
                  {stats.embedding_model}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Kolekcja Qdrant</p>
                <p className="text-sm font-mono text-slate-700 dark:text-slate-300">
                  {stats.collection_name}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <ConfigPill active={stats.rerank_enabled} label="Cross-encoder rerank" />
                <ConfigPill active={stats.expand_enabled} label="Query expansion" />
              </div>
              {stats.last_ingest && (
                <p className="text-xs text-slate-400 dark:text-slate-500 pt-1">
                  Ostatni ingest:{" "}
                  <span className="font-medium text-slate-600 dark:text-slate-300">
                    {new Date(stats.last_ingest).toLocaleString("pl-PL")}
                  </span>
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Ładowanie…</p>
          )}
        </div>
      </div>

      {/* Source breakdown bar chart */}
      {stats && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
              Podział według źródła
            </h3>
            <span className="text-sm font-bold text-slate-700 dark:text-slate-300">
              {stats.total_chunks.toLocaleString("pl-PL")} chunków łącznie
            </span>
          </div>
          <SourceBreakdownChart breakdown={stats.by_source} />
        </div>
      )}

      {/* Per-source cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {SOURCE_META.filter(({ key }) => (stats.by_source[key] ?? 0) > 0).map(({ key, label, badge }) => (
            <div
              key={key}
              className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm"
            >
              <p className={`text-xs font-medium px-2 py-0.5 rounded-full inline-block mb-2 ${badge}`}>
                {label}
              </p>
              <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">
                {(stats.by_source[key] ?? 0).toLocaleString("pl-PL")}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
