export interface SourceDocument {
  score: number;
  act_id: string;
  title: string;
  year: string;
  publisher: string;
  pos: string;
  url: string;
  chunk_index: number;
  text: string;
  citation: string;
}

export interface AskResponse {
  question: string;
  answer: string;
  sources: SourceDocument[];
  model_used: string;
  retrieval_used: boolean;
}

export interface AskRequest {
  question: string;
  top_k?: number;
  year_filter?: string | null;
  publisher_filter?: string | null;
  use_rag?: boolean;
}

export interface HealthResponse {
  status: string;
  qdrant_connected: boolean;
  model_loaded: boolean;
  embedding_model_loaded: boolean;
  collection_count: number | null;
}

export interface HistoryEntry {
  id: string;
  timestamp: string;
  question: string;
  answer: string;
  sources: SourceDocument[];
  model_used: string;
  retrieval_used: boolean;
}
