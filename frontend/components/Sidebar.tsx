"use client";

import { useState, useEffect } from "react";
import { getHistory } from "@/lib/history";
import type { HistoryEntry } from "@/lib/types";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  onSelectQuestion: (question: string) => void;
}

export function Sidebar({ open, onClose, onSelectQuestion }: SidebarProps) {
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (open) {
      getHistory().then(setHistory);
    }
  }, [open]);

  function formatDate(iso: string) {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMin = Math.floor(diffMs / 60_000);
      if (diffMin < 1) return "przed chwilą";
      if (diffMin < 60) return `${diffMin} min temu`;
      const diffH = Math.floor(diffMin / 60);
      if (diffH < 24) return `${diffH} godz. temu`;
      return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" });
    } catch {
      return "";
    }
  }

  return (
    <>
      {/* Sidebar panel */}
      <aside
        className={`fixed top-0 left-0 z-30 h-full w-72 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 shadow-xl transition-transform duration-300 ease-in-out flex flex-col ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="font-semibold text-slate-800 dark:text-slate-200">Historia</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            aria-label="Zamknij"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* History list */}
        <div className="flex-1 overflow-y-auto py-2">
          {history.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-8 px-4">
              Brak historii zapytań.
            </p>
          ) : (
            <ul className="space-y-0.5 px-2">
              {history.map((entry) => (
                <li key={entry.id}>
                  <button
                    onClick={() => onSelectQuestion(entry.question)}
                    className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors group"
                  >
                    <p className="text-sm text-slate-700 dark:text-slate-300 line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                      {entry.question}
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                      {formatDate(entry.timestamp)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer links */}
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3 flex gap-3 text-sm">
          <a
            href="/history"
            className="text-blue-600 dark:text-blue-400 hover:underline"
            onClick={onClose}
          >
            Pełna historia
          </a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <a
            href="/admin"
            className="text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            onClick={onClose}
          >
            Admin
          </a>
        </div>
      </aside>
    </>
  );
}
