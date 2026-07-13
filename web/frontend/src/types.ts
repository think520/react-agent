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
  artifacts?: WikiArtifact[];
}

export interface ChatSessionSummary {
  chat_session_id: string;
  name: string;
  name_source: "ai" | "fallback" | "manual";
  created_at: string;
  last_active: string;
  message_count: number;
  library_id?: string | null;
}

export interface LibrarySummary {
  library_id: string;
  name: string;
  created_at: string;
  last_opened_at: string;
  active: boolean;
  available: boolean;
}

export interface LibraryMigrationPreview {
  folder_name: string;
  already_initialized: boolean;
  material_count: number;
  size_bytes: number;
  wiki_pages: number;
  legacy_source_count: number;
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

export type WikiChangeKind = "add" | "update" | "merge" | "conflict" | "skip";

export interface WikiPlanChange {
  change_id: string;
  kind: WikiChangeKind;
  title: string;
  page_type: "wiki_entity" | "wiki_concept";
  summary: string;
  related: string[];
  source_count: number;
  target: string;
  content: string;
}

export interface WikiPlan {
  plan_id: string;
  status: "planned" | "applied";
  action: "generate" | "update";
  instruction: string;
  created_at: string;
  applied_at?: string;
  checkpoint_id?: string;
  scope: { document_ids: string[]; documents: string[] };
  summary: Record<WikiChangeKind, number>;
  changes: WikiPlanChange[];
  written?: string[];
}

export interface WikiFocusArtifact {
  artifact_id: string;
  type: "wiki_focus";
  library_id?: string | null;
  operation: "generate" | "update" | "repair" | "migrate";
  status: "awaiting_confirmation" | "confirmed" | "cancelled";
  summary: string;
  instruction: string;
  scope: { document_ids: string[]; wiki_document_ids?: string[]; course?: string | null; documents: string[] };
}

export interface WikiPlanArtifact {
  artifact_id: string;
  type: "wiki_plan";
  library_id?: string | null;
  operation: string;
  status: "planned" | "applied";
  plan_id: string;
  plan: WikiPlan;
}

export interface WikiResultArtifact {
  artifact_id: string;
  type: "wiki_result";
  library_id?: string | null;
  operation: "apply" | "restore";
  status: "applied" | "restored";
  plan_id?: string;
  checkpoint_id?: string;
  written?: string[];
  restored_at?: string;
}

export type WikiArtifact = WikiFocusArtifact | WikiPlanArtifact | WikiResultArtifact;
