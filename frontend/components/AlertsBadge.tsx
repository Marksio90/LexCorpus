"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export function AlertsBadge() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    fetch("/api/alerts")
      .then((r) => r.ok ? r.json() : [])
      .then((alerts: { read: boolean }[]) =>
        setCount(alerts.filter((a) => !a.read).length)
      );
  }, []);

  return (
    <Link
      href="/alerts"
      className="relative text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors text-sm"
    >
      Alerty
      {count > 0 && (
        <span className="absolute -top-1.5 -right-3 bg-red-500 text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </Link>
  );
}
