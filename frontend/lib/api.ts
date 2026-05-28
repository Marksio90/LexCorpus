import type { AskRequest, AskResponse, HealthResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function askQuestion(
  question: string,
  topK = 5,
  options?: Partial<Omit<AskRequest, "question" | "top_k">>
): Promise<AskResponse> {
  const body: AskRequest = {
    question,
    top_k: topK,
    use_rag: true,
    year_filter: null,
    publisher_filter: null,
    ...options,
  };

  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let message = `Błąd serwera: ${res.status}`;
    try {
      const err = await res.json();
      if (err.detail) message = err.detail;
    } catch {
      // ignore parse error
    }
    throw new Error(message);
  }

  return res.json() as Promise<AskResponse>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_URL}/health`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Błąd połączenia z API: ${res.status}`);
  }

  return res.json() as Promise<HealthResponse>;
}
