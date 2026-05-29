import type { AskRequest, AskResponse, AnswerConfidence, HealthResponse, SearchRequest, SearchResponse, SourceDocument, StatsResponse, SyncStatus } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface StreamCallbacks {
  onSources: (sources: SourceDocument[], retrievalUsed: boolean) => void;
  onDelta: (text: string) => void;
  onDone: (modelUsed: string, confidence?: AnswerConfidence) => void;
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
          callbacks.onDone(event.model_used, event.confidence);
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

export async function searchDocuments(
  query: string,
  topK = 10,
  options?: Partial<Omit<SearchRequest, "query" | "top_k">>
): Promise<SearchResponse> {
  const body: SearchRequest = { query, top_k: topK, ...options };
  const res = await fetch(`${API_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Błąd wyszukiwania: ${res.status}`);
  return res.json() as Promise<SearchResponse>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Błąd połączenia z API: ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}

export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch(`${API_URL}/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Błąd pobierania statystyk: ${res.status}`);
  return res.json() as Promise<StatsResponse>;
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${API_URL}/sync/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Błąd pobierania statusu sync: ${res.status}`);
  return res.json() as Promise<SyncStatus>;
}

export async function triggerSync(): Promise<{ ok: boolean; detail: string }> {
  const res = await fetch(`${API_URL}/sync/trigger`, { method: "POST" });
  if (!res.ok) throw new Error(`Błąd uruchamiania sync: ${res.status}`);
  return res.json();
}
