import type { AskRequest, AskResponse, HealthResponse, SourceDocument } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface StreamCallbacks {
  onSources: (sources: SourceDocument[], retrievalUsed: boolean) => void;
  onDelta: (text: string) => void;
  onDone: (modelUsed: string) => void;
  onError: (detail: string) => void;
}

export async function askQuestionStream(
  question: string,
  topK = 5,
  callbacks: StreamCallbacks,
  options?: Partial<Omit<AskRequest, "question" | "top_k">>
): Promise<void> {
  const body: AskRequest = {
    question,
    top_k: topK,
    use_rag: true,
    year_filter: null,
    publisher_filter: null,
    ...options,
  };

  const res = await fetch(`${API_URL}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    let message = `Błąd serwera: ${res.status}`;
    try {
      const err = await res.json();
      if (err.detail) message = err.detail;
    } catch { /* ignore */ }
    throw new Error(message);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.type === "sources") {
          callbacks.onSources(event.sources, event.retrieval_used);
        } else if (event.type === "delta") {
          callbacks.onDelta(event.text);
        } else if (event.type === "done") {
          callbacks.onDone(event.model_used);
        } else if (event.type === "error") {
          callbacks.onError(event.detail);
        }
      } catch { /* malformed SSE line, skip */ }
    }
  }
}

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
