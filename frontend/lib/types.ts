// Mirrors api/serialize.py's response shapes exactly. Kept in one place so every component reads
// the same contract the FastAPI backend actually returns.

export type Tier = "gold" | "ai_checked" | "silver" | string;

export interface DocumentChunkJSON {
  doc_id: string;
  scheme_id: string;
  effective_date: string | null;
  citation: string;
  source_path: string;
  chunk_index: number;
  text: string;
  source_type: string;
  supersedes_doc_id: string | null;
  supersedes_effective_date: string | null;
}

export interface NextStepsJSON {
  benefits_text: string | null;
  application_process_text: string | null;
  official_link: string | null;
  source: string;
}

export type MessageKind =
  | "text"
  | "scheme_intro"
  | "shortlist"
  | "question"
  | "verdict"
  | "scheme_detail";

export interface ChatMessage {
  role: "user" | "assistant";
  kind: MessageKind;
  text: string;
  // present only on specific kinds -- see chat_engine.py's own _say() call sites
  scheme_id?: string;
  tier?: Tier;
  items?: DocumentChunkJSON[];
  quick_replies?: string[] | null;
  verdict_value?: "eligible" | "ineligible" | "undetermined_missing_facts";
  headline?: string;
  trace?: Record<string, unknown>;
  plain_explanation?: string;
  next_steps?: NextStepsJSON;
  record?: {
    scheme_name?: string | null;
    description?: string | null;
    eligibility_text?: string | null;
    [key: string]: unknown;
  };
}

export interface PendingQuestion {
  field: string;
  member: string;
  answer_type: "boolean" | "number" | "text";
  prompt: string;
  quick_replies: string[] | null;
}

export interface ChatResponse {
  session_id: string;
  messages: ChatMessage[];
  pending_question: PendingQuestion | null;
  current_scheme_id: string | null;
  current_scheme_tier: string | null;
}

export interface ExampleCard {
  label: string;
  description: string;
  scheme_id: string;
}

export interface SchemeRow {
  id: string;
  name: string;
  source_type: "gold" | "silver";
  description: string | null;
  categories: string[];
}

export interface SchemeListResponse {
  total: number;
  categories: string[];
  results: SchemeRow[];
}
