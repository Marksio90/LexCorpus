"use client";

import { useEffect, useState } from "react";

interface AnalyticsData {
  totalQueries:   number;
  queriesLast7:   number;
  queriesLast30:  number;
  chart:          { date: string; count: number }[];
  sourceCounts:   Record<string, number>;
  alertsTotal:    number;
  alertsUnread:   number;
  registrySubs:   number;
  expertRequests: number;
  tier:           string;
}

const SOURCE_LABELS: Record<string, string> = {
  legislation:     "Ustawa / Rozporządzenie",
  judgment_nsa:    "NSA / WSA",
  judgment_sn:     "Sąd Najwyższy",
  judgment_tk:     "Trybunał Konstytucyjny",
  judgment_common: "Sąd powszechny",
  judgment_kio:    "KIO",
};

const SOURCE_COLORS: Record<string, string> = {
  legislation:     "bg-blue-500",
  judgment_nsa:    "bg-purple-500",
  judgment_sn:     "bg-indigo-500",
  judgment_tk:     "bg-red-500",
  judgment_common: "bg-slate-400",
  judgment_kio:    "bg-orange-500",
};

const TIER_LABEL: Record<string, string> = { free: "Free", pro: "Pro", kancelaria: "Kancelaria" };

function StatCard({ label, value, sub, href }: { label: string; value: number | string; sub?: string; href?: string }) {
  const content = (
    <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5 hover:shadow-sm transition-shadow">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">{label}</p>
      <p className="text-3xl font-bold text-slate-900 dark:text-slate-100">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  );
  return href ? <a href={href} className="block">{content}</a> : content;
}

function ActivityChart({ chart }: { chart: { date: string; count: number }[] }) {
  const max = Math.max(...chart.map((c) => c.count), 1);
  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
      <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-4">Aktywność — ostatnie 30 dni</h2>
      <div className="flex items-end gap-0.5 h-24">
        {chart.map((c) => {
          const pct = Math.round((c.count / max) * 100);
          const isToday = c.date === new Date().toISOString().slice(0, 10);
          return (
            <div
              key={c.date}
              className="flex-1 group relative flex flex-col justify-end"
              title={`${c.date}: ${c.count} pytań`}
            >
              <div
                className={`rounded-sm transition-all ${isToday ? "bg-blue-600" : "bg-blue-300 dark:bg-blue-700 group-hover:bg-blue-500"}`}
                style={{ height: `${Math.max(pct, c.count > 0 ? 4 : 1)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-2 text-xs text-slate-400">
        <span>{chart[0]?.date.slice(5)}</span>
        <span>dziś</span>
      </div>
    </div>
  );
}

function SourcesChart({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
      <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-4">
        Używane źródła (ostatnie 30 dni)
      </h2>
      <div className="space-y-3">
        {sorted.map(([type, count]) => {
          const pct = Math.round((count / total) * 100);
          const color = SOURCE_COLORS[type] ?? "bg-slate-400";
          return (
            <div key={type}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-600 dark:text-slate-400">{SOURCE_LABELS[type] ?? type}</span>
                <span className="text-slate-500 dark:text-slate-400 tabular-nums">{count} ({pct}%)</span>
              </div>
              <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const [data,    setData]    = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/analytics")
      .then((r) => r.json())
      .then((d: AnalyticsData) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Twoje statystyki</h1>
          {data && (
            <span className="ml-auto text-xs px-2.5 py-1 rounded-full font-semibold bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
              {TIER_LABEL[data.tier] ?? data.tier}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : !data ? (
          <p className="text-center text-slate-400 py-12">Błąd ładowania danych.</p>
        ) : (
          <>
            {/* KPI cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Pytań łącznie"     value={data.totalQueries}  href="/history" />
              <StatCard label="Pytań (7 dni)"     value={data.queriesLast7}                 />
              <StatCard label="Pytań (30 dni)"    value={data.queriesLast30}                />
              <StatCard
                label="Alerty prawne"
                value={data.alertsTotal}
                sub={data.alertsUnread > 0 ? `${data.alertsUnread} nieprzeczytanych` : "wszystkie przeczytane"}
                href="/alerts"
              />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <StatCard label="Subskrypcje rejestru" value={data.registrySubs}   href="/registry" />
              <StatCard label="Pytania do ekspertów" value={data.expertRequests} href="/expert" />
              <StatCard
                label="Wszystkie funkcje"
                value="→"
                sub="Przeglądaj narzędzia"
                href="/ask"
              />
            </div>

            {/* Activity chart */}
            <ActivityChart chart={data.chart} />

            {/* Sources chart */}
            <SourcesChart counts={data.sourceCounts} />

            {/* Feature map */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6">
              <h2 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-4">Wszystkie narzędzia</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: "Asystent prawny",       href: "/ask",        icon: "⚖️" },
                  { label: "Wyszukiwarka",           href: "/search",     icon: "🔍" },
                  { label: "Kreator dokumentów",    href: "/draft",      icon: "📝" },
                  { label: "Analiza dokumentów",    href: "/analyze",    icon: "🔬" },
                  { label: "Wyszukiwarka precedensów", href: "/precedents", icon: "📚" },
                  { label: "Monitoring rejestru",   href: "/registry",   icon: "🔔" },
                  { label: "Historia zmian",        href: "/timeline",   icon: "📅" },
                  { label: "Alerty prawne",         href: "/alerts",     icon: "🚨" },
                  { label: "Zapytaj eksperta",      href: "/expert",     icon: "👨‍⚖️" },
                  { label: "Historia pytań",        href: "/history",    icon: "🕐" },
                  { label: "Moje dokumenty",        href: "/account/documents", icon: "📁" },
                  { label: "Ustawienia",            href: "/account/settings",  icon: "⚙️" },
                ].map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors group"
                  >
                    <span className="text-lg">{item.icon}</span>
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                      {item.label}
                    </span>
                  </a>
                ))}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
