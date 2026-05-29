/**
 * Historia zapytań — server-side (SQLite przez /api/history).
 * Sygnatura zachowana dla zgodności z istniejącym kodem.
 */
import type { HistoryEntry, AskResponse } from "./types";

// ── Server API helpers ────────────────────────────────────────────────────────

export async function getHistory(): Promise<HistoryEntry[]> {
  try {
    const res = await fetch("/api/history", { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as HistoryEntry[];
  } catch {
    return [];
  }
}

export async function saveToHistory(response: AskResponse): Promise<HistoryEntry | null> {
  try {
    const res = await fetch("/api/history", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question:       response.question,
        answer:         response.answer,
        sources:        response.sources,
        model_used:     response.model_used,
        retrieval_used: response.retrieval_used,
      }),
    });
    if (!res.ok) return null;
    const { id, timestamp } = await res.json() as { id: string; timestamp: string };
    return {
      id,
      timestamp,
      question:       response.question,
      answer:         response.answer,
      sources:        response.sources,
      model_used:     response.model_used,
      retrieval_used: response.retrieval_used,
    };
  } catch {
    return null;
  }
}

export async function clearHistory(): Promise<void> {
  await fetch("/api/history", { method: "DELETE" });
}

export async function removeHistoryEntry(id: string): Promise<void> {
  await fetch(`/api/history/${id}`, { method: "DELETE" });
}
