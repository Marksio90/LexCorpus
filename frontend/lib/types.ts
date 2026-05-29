export type SourceType =
  | "legislation"
  | "judgment_nsa"
  | "judgment_sn"
  | "judgment_tk"
  | "judgment_common"
  | "judgment_kio"
  | "tax_interpretation"
  | "unknown";

export type FeedbackRating = 1 | -1;

export interface FeedbackResponse {
  id: string;
  rating: FeedbackRating;
}

export interface SourceDocument {
  score: number;
  act_id: string;
  title: string;
  year: string;
  publisher: string;
  source_type: SourceType;
  pos: string;
  url: string;
  chunk_index: number;
  total_chunks: number;
  text: string;
  citation: string;
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  year_filter?: string | null;
  publisher_filter?: string | null;
  source_type_filter?: SourceType | null;
}

export interface SearchResponse {
  query: string;
  results: SourceDocument[];
  total: number;
}

export interface AnswerConfidence {
  score:            number;
  level:            "wysoka" | "średnia" | "niska";
  n_sources:        number;
  top_source_score: number;
  explanation:      string;
}

export interface AskResponse {
  question:       string;
  answer:         string;
  sources:        SourceDocument[];
  model_used:     string;
  retrieval_used: boolean;
  confidence?:    AnswerConfidence;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AskRequest {
  question: string;
  top_k?: number;
  year_filter?: string | null;
  publisher_filter?: string | null;
  source_type_filter?: SourceType | null;
  use_rag?: boolean;
  history?: ConversationTurn[];
}

export interface HealthResponse {
  status: string;
  qdrant_connected: boolean;
  model_loaded: boolean;
  embedding_model_loaded: boolean;
  collection_count: number | null;
}

export interface SourceBreakdown {
  legislation: number;
  judgment_nsa: number;
  judgment_sn: number;
  judgment_tk: number;
  judgment_common: number;
  judgment_kio: number;
  tax_interpretation: number;
  total: number;
}

export interface SyncStatus {
  last_run_start: string | null;
  last_run_end: string | null;
  last_run_ok: boolean | null;
  last_run_log: string[];
  next_run: string | null;
  running: boolean;
  runs_total: number;
  runs_failed: number;
}

export interface StatsResponse {
  by_source: SourceBreakdown;
  total_chunks: number;
  collection_name: string;
  embedding_model: string;
  rerank_enabled: boolean;
  expand_enabled: boolean;
  last_ingest: string | null;
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
