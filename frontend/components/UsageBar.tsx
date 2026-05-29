"use client";

import { useEffect, useState } from "react";

interface Usage {
  used:  number;
  limit: number;
  tier:  string;
}

const TIER_LABELS: Record<string, string> = {
  free:       "Free",
  pro:        "Pro",
  kancelaria: "Kancelaria",
};

export function UsageBar() {
  const [usage,   setUsage]   = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/usage")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setUsage(d); })
      .finally(() => setLoading(false));
  }, []);

  if (loading || !usage) return null;

  const pct     = Math.min((usage.used / usage.limit) * 100, 100);
  const near    = pct >= 80;
  const reached = usage.used >= usage.limit;

  return (
    <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 min-w-0">
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[11px] font-medium ${
        usage.tier === "pro"        ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300" :
        usage.tier === "kancelaria" ? "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300" :
        "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
      }`}>
        {TIER_LABELS[usage.tier] ?? usage.tier}
      </span>

      <div className="flex items-center gap-1.5 min-w-0">
        <div className="w-20 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden shrink-0">
          <div
            className={`h-full rounded-full transition-all ${
              reached ? "bg-red-500" : near ? "bg-yellow-500" : "bg-blue-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={reached ? "text-red-500 font-medium" : ""}>
          {usage.used}/{usage.limit === 9999 ? "∞" : usage.limit}
        </span>
      </div>

      {reached && usage.tier === "free" && (
        <a
          href="/upgrade"
          className="shrink-0 text-[11px] bg-blue-600 text-white px-2 py-0.5 rounded hover:bg-blue-700 transition-colors font-medium"
        >
          Upgrade
        </a>
      )}
    </div>
  );
}
