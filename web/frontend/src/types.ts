export type AttributionKind = "local" | "local_extension" | "web" | "ai" | "unverified";

export interface SourceRef {
  source_type: "local" | "web";
  source_id: string;
  title: string;
  url?: string | null;
  document_id?: string | null;
  chunk_id?: string | null;
  heading?: string | null;
  page?: number | null;
  slide?: number | null;
  collection?: "material" | "wiki" | null;
}

export interface Attribution {
  kind: AttributionKind;
  sources: SourceRef[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  attribution?: Attribution;
  pending?: boolean;
  failed?: boolean;
  process?: Array<{ phase: string; message: string; toolName?: string; elapsed?: number }>;
}

export interface ChatSessionSummary {
  chat_session_id: string;
  name: string;
  name_source: "ai" | "fallback" | "manual";
  created_at: string;
  last_active: string;
  message_count: number;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  messages: ChatMessage[];
}

export interface DocumentSummary {
  document_id: string;
  source: string;
  kind: string;
  title: string;
  course?: string | null;
  summary?: string;
  vector_status?: string;
  vector_error?: string | null;
  updated_at?: string;
  managed?: boolean;
  origin?: "managed" | "workspace" | "legacy_index" | string;
  chunk_count?: number;
  collection: "material" | "wiki";
  wiki_type?: "entity" | "concept" | null;
  canonical_id?: string | null;
  content_role: "content" | "metadata";
}

export interface DocumentSection {
  chunk_id: string;
  heading?: string;
  page_start?: number | null;
  slide_start?: number | null;
  text: string;
}

export interface Question {
  id: number;
  type: "single_choice" | "true_false" | "short_answer" | string;
  type_label: string;
  question: string;
  options?: string[] | null;
  concepts?: string[];
  difficulty?: string;
  attribution?: Attribution;
}

export interface PracticeSession {
  practice_session_id: number;
  status: string;
  questions: Question[];
  attempts: Array<{
    question_id: number;
    user_answer: string;
    is_correct: boolean;
    feedback: string;
  }>;
  progress: {
    answered: number;
    total: number;
    correct: number;
    current_index: number;
    completed: boolean;
  };
}

export interface ReviewQueue {
  due_concepts: Array<Record<string, unknown>>;
  wrong_answers: Array<Record<string, unknown>>;
  weaknesses: Array<Record<string, unknown>>;
}

export interface SettingsSummary {
  workspace_name: string;
  default_provider: string;
  providers: Array<{ name: string; configured: boolean; type?: string }>;
  mcp_enabled: boolean;
  skills: Array<{ name: string; description: string }>;
}

export interface WikiHealth {
  healthy: boolean;
  total_pages: number;
  orphan_count: number;
  broken_link_count: number;
  missing_count: number;
  stale_count: number;
  vaults: Array<{
    vault: string;
    total_pages: number;
    orphans: string[];
    broken_links: Array<{ source: string; target: string }>;
    missing: string[];
    stale: string[];
    errors: string[];
    healthy: boolean;
  }>;
}
