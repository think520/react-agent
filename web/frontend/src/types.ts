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
  wiki_type?: "source" | "entity" | "concept" | "analysis" | "question" | "note" | null;
  domain?: string | null;
  accessed_at?: string | null;
  snapshot_id?: string | null;
  reader?: "direct" | "jina" | null;
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
  artifacts?: ChatArtifact[];
  references?: ChatReference[];
  personalization?: PersonalizationRef[];
}

export interface PersonalizationRef {
  id: string;
  title: string;
  scope: "global" | "library";
  kind: KnowledgeKind | "mastery";
  content: string;
  updated_at: string;
}

export interface ChatReference {
  type: "document" | "session";
  id: string;
  title: string;
  collection?: "material" | "wiki";
}

export interface ChatSessionSummary {
  chat_session_id: string;
  name: string;
  name_source: "ai" | "fallback" | "manual";
  created_at: string;
  last_active: string;
  message_count: number;
  library_id?: string | null;
  provider_name?: string | null;
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
  wiki_type?: "source" | "entity" | "concept" | "analysis" | "question" | "note" | null;
  canonical_id?: string | null;
  content_role: "content" | "metadata";
  wiki_coverage?: WikiDocumentCoverage;
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
  origin: "practice" | "review" | "chat";
  personalization?: PersonalizationRef[];
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
  personalization?: PersonalizationRef[];
}

export interface SettingsSummary {
  workspace_name: string;
  default_provider: string;
  providers: Array<{ name: string; configured: boolean; type?: string; model?: string; is_default?: boolean; api_key_env?: string; preset?: string; base_url?: string }>;
  search_providers: Array<{ name: "auto" | "tavily" | "exa"; configured: boolean }>;
  mcp_enabled: boolean;
  skills: Array<{
    name: string;
    description: string;
    enabled: boolean;
    source: string;
    capabilities: string[];
  }>;
  preferences: UserPreferences;
}

export interface UserPreferences {
  schema_version: 4;
  revision: number;
  assistant: {
    display_name: string;
    teaching_style: "guided" | "explanatory" | "practice";
    answer_depth: "concise" | "standard" | "deep";
    feedback_strength: "gentle" | "direct";
  };
  user: {
    display_name: string;
    profile: string;
    long_term_goal: string;
  };
  appearance: {
    reading_font: "jin-kai" | "noto-serif";
    body_font_size: 15 | 16 | 17 | 18;
    content_width: 640 | 720 | 800;
    paper_texture: boolean;
    session_density: "comfortable" | "compact";
    motion: "system" | "reduced";
  };
  ai: {
    default_provider: string;
    task_providers: { wiki_discovery: string; wiki_drafting: string };
  };
  wiki: {
    default_mode: WikiGenerationMode;
    guide_completed: boolean;
    budget: WikiRunBudget;
  };
  memory: { enabled: boolean };
  search: { provider: "auto" | "tavily" | "exa"; permission: "ask" | "auto"; jina_fallback: boolean };
  skills: { enabled_names: string[] };
}

export type KnowledgeKind = "preference" | "goal" | "profile_fact" | "learning_strategy" | "course_insight" | "study_pattern";

export interface PersonalKnowledgeItem {
  id: string;
  scope: "global" | "library";
  kind: KnowledgeKind;
  title: string;
  content: string;
  pinned: boolean;
  confidence: number;
  evidence: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  revision: number;
}

export interface KnowledgeCandidate {
  id: string;
  scope: "global" | "library";
  kind: KnowledgeKind;
  operation: "create" | "update";
  title: string;
  content: string;
  target_item_id?: string | null;
  confidence: number;
  reason: string;
  evidence: Array<Record<string, unknown>>;
  status: "pending" | "confirmed" | "rejected" | "superseded";
  created_at: string;
  updated_at: string;
}

export interface LearningEvent {
  id: string;
  type: "quiz_answered" | "practice_completed" | "review_started" | "review_completed" | "document_opened" | "reading_progress" | "chat_completed";
  source_type: "quiz" | "review" | "document" | "chat";
  source_id: string;
  concept?: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface MemoryOverview {
  knowledge_count: number;
  global_count: number;
  library_count: number;
  pending_candidate_count: number;
  event_count: number;
  jobs: { pending: number; failed: number };
}

export interface LegacyMemoryPreview {
  entries: Array<{
    name: string;
    type: string;
    description: string;
    content_preview: string;
    suggested_scope: "global" | "library";
    suggested_kind: KnowledgeKind;
  }>;
  daily_files: string[];
}

export interface RuntimeStatus {
  backend: "connected" | "disconnected";
  version: string;
  active_library: LibrarySummary | null;
  knowledge: { state: "ready" | "empty" | "not_selected"; documents: number };
  memory: { enabled: boolean };
  skills: { enabled: number; available: number };
  providers: { configured: number; available: number; default: string };
  search: { default: string; permission: "ask" | "auto"; tavily_configured: boolean; exa_configured: boolean; jina_fallback: boolean };
}

export interface WikiHealth {
  healthy: boolean;
  total_pages: number;
  orphan_count: number;
  broken_link_count: number;
  missing_count: number;
  stale_count: number;
  duplicate_candidate_count?: number;
  semantic_candidate_count?: number;
  vaults: Array<{
    vault: string;
    total_pages: number;
    orphans: string[];
    broken_links: Array<{ source: string; target: string }>;
    missing: string[];
    stale: string[];
    index_mismatches?: string[];
    contradiction_candidates?: string[];
    duplicate_candidates?: Array<{ canonical_title: string; pages: string[] }>;
    semantic_candidates?: Array<{ type: string; pages: string[]; reason: string }>;
    errors: string[];
    healthy: boolean;
  }>;
}

export type WikiChangeKind = "add" | "update" | "merge" | "conflict" | "skip" | "split";

export type WikiScopeMode = "uncovered" | "smart_library" | "selected_only" | "course";
export type WikiGenerationMode = "catalog" | "standard" | "deep";
export type WikiCoverageStatus = "uncovered" | "partial" | "covered" | "stale";

export interface WikiRunBudget {
  max_requests: number;
  max_input_tokens: number;
  max_output_tokens: number;
}

export interface WikiRunEstimate {
  generation_mode: WikiGenerationMode;
  document_count: number;
  batch_count: number;
  estimated_pages: [number, number];
  request_range: [number, number];
  input_token_range: [number, number];
  output_token_range: [number, number];
  duration_range_seconds: [number, number];
  rough: boolean;
  confidence: "low" | "medium" | "high";
  historical_sample_size: number;
  local_cache_reuse_included: boolean;
  assumptions: string[];
  provider: string;
  model: string;
}

export interface WikiDocumentCoverage {
  document_id: string;
  status: WikiCoverageStatus;
  source_page_id?: string | null;
  linked_page_count: number;
  source_fingerprint: string;
  covered_at?: string | null;
}

export interface WikiPlanChange {
  change_id: string;
  kind: WikiChangeKind;
  title: string;
  page_type: "wiki_source" | "wiki_entity" | "wiki_concept" | "wiki_analysis" | "wiki_question" | "wiki_note";
  summary: string;
  related: string[];
  source_count: number;
  target: string;
  content: string;
}

export interface WikiPlan {
  plan_id: string;
  run_id?: string;
  status: "planning" | "planned" | "applied" | "replaced" | "cancelled" | "failed" | "paused_budget";
  action: "generate" | "update";
  instruction: string;
  created_at: string;
  applied_at?: string;
  checkpoint_id?: string;
  topic?: string;
  scope: {
    mode?: WikiScopeMode;
    seed_document_ids?: string[];
    document_ids: string[];
    discovered_document_ids?: string[];
    documents: string[];
  };
  summary: Record<WikiChangeKind, number>;
  changes: WikiPlanChange[];
  batches?: Array<{ batch_id: string; index: number; document_ids: string[]; documents: string[]; status: string }>;
  coverage_before?: WikiDocumentCoverage[];
  phase?: "queued" | "discovering" | "drafting" | "planned" | "cancelling" | "cancelled" | "failed" | "interrupted" | "paused_budget";
  completed_batches?: number;
  total_batches?: number;
  completed_pages?: number;
  total_pages?: number;
  error?: string;
  written?: string[];
  task_id?: string;
  last_error?: string;
  staging?: Array<{ change_id: string; path: string; errors: string[] }>;
  replacement_plan_id?: string;
  recovery?: { strategy: "keep_existing"; resolved_at: string; skipped_titles: string[] };
  generation_mode?: WikiGenerationMode;
  budget?: WikiRunBudget;
  usage?: {
    requests: number;
    input_tokens: number;
    output_tokens: number;
    cache_hits: number;
    duration_ms?: number;
    provider_cache_read_tokens?: number;
    provider_cache_miss_tokens?: number;
  };
  remaining_pages?: number;
  remaining_document_ids?: string[];
}

export interface WikiRepairPlan {
  plan_id: string;
  status: "planned" | "drafting" | "applied" | "partial" | "cancelled";
  health_snapshot: WikiHealth;
  items: Array<{
    item_id: string;
    issue_type: string;
    page_id?: string | null;
    title: string;
    execution: "local" | "ai" | "manual";
    resolution: "reindex" | "relink" | "merge" | "archive" | "regenerate" | "review";
    status: "pending" | "ready" | "applied" | "skipped" | "failed";
  }>;
  checkpoint_id?: string;
  applied_count?: number;
  pending_count?: number;
  ai_review?: Array<{ pages?: string[]; issue_type?: string; reason?: string; suggestion?: string }>;
}

export interface WikiEditablePage {
  document_id: string;
  title: string;
  body: string;
  tags: string[];
  related: string[];
  page_type: WikiPlanChange["page_type"];
  generated_by: "bobodan" | "user" | string;
  managed_by: "ai" | "user" | "mixed";
  content_revision: number;
  source_refs: Array<Record<string, unknown>>;
}

export interface DocumentImpact {
  document_id: string;
  title: string;
  affected_count: number;
  affected_pages: Array<{
    title: string;
    page_type: string;
    target: string;
    source_count: number;
    action: "archive_candidate" | "mark_needs_update";
  }>;
}

export interface WikiTask {
  task_id: string;
  operation: "plan" | "apply" | string;
  status: "running" | "completed" | "failed" | "cancelled";
  attempts: number;
  retryable: boolean;
  error?: string;
  plan_id?: string;
  created_at: string;
  updated_at: string;
}

export interface WikiFocusArtifact {
  artifact_id: string;
  type: "wiki_focus";
  library_id?: string | null;
  operation: "generate" | "update" | "repair" | "migrate";
  status: "awaiting_confirmation" | "confirmed" | "cancelled";
  summary: string;
  instruction: string;
  scope: {
    orchestrated?: boolean;
    mode?: WikiScopeMode;
    seed_document_ids?: string[];
    document_ids: string[];
    wiki_document_ids?: string[];
    course?: string | null;
    topic?: string;
    documents: string[];
    coverage?: WikiDocumentCoverage[];
  };
}

export interface WikiPlanArtifact {
  artifact_id: string;
  type: "wiki_plan";
  library_id?: string | null;
  operation: string;
  status: "planning" | "planned" | "applied" | "replaced" | "cancelled" | "failed" | "paused_budget";
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
  kept_existing?: string[];
  restored_at?: string;
}

export type WikiArtifact = WikiFocusArtifact | WikiPlanArtifact | WikiResultArtifact;

export interface SettingsChangeArtifact {
  artifact_id: string;
  type: "settings_change";
  proposal_id: string;
  status: "pending" | "applied" | "rejected";
  changes: Array<{ key: string; label: string; before: unknown; after: unknown }>;
}

export interface WebConsentArtifact {
  artifact_id: string;
  type: "web_consent";
  status: "pending" | "approved" | "rejected";
  query: string;
  reason: string;
}

export interface WebSourceCandidate {
  candidate_id: string;
  title: string;
  url: string;
  domain: string;
  snippet: string;
  published_at?: string | null;
  rank: number;
  provider: string;
  quality_hint: "official" | "reference" | "community" | "unknown";
}

export interface WebCandidatesArtifact {
  artifact_id: string;
  type: "web_candidates";
  search_id: string;
  status: "ready" | "fetching" | "partial" | "failed" | "used";
  query: string;
  provider: string;
  candidates: WebSourceCandidate[];
  selected_candidate_ids?: string[];
  error_kind?: string;
}

export interface WebEvidenceArtifact {
  artifact_id: string;
  type: "web_evidence";
  research_id: string;
  status: "ready" | "partial" | "failed";
  sources: SourceRef[];
  failed_source_ids: string[];
}

export interface PracticeReadyArtifact {
  artifact_id: string;
  type: "practice_ready";
  status: "ready" | "started";
  topic: string;
  question_ids: number[];
  count: number;
  attribution: Attribution;
  practice_session_id?: number;
  chat_session_id?: string;
  personalization?: PersonalizationRef[];
}

export interface MemoryConfirmationArtifact {
  artifact_id: string;
  type: "memory_confirmation";
  status: "pending" | "confirmed" | "rejected";
  scope: "global" | "library";
  kind: KnowledgeKind;
  title: string;
  content: string;
  target_item_id?: string | null;
  before?: PersonalKnowledgeItem | null;
  requires_warning: boolean;
  knowledge_item_id?: string;
}

export type WebArtifact = WebConsentArtifact | WebCandidatesArtifact | WebEvidenceArtifact;
export type ChatArtifact = WikiArtifact | SettingsChangeArtifact | WebArtifact | PracticeReadyArtifact | MemoryConfirmationArtifact;
