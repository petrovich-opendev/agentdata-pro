export interface User {
  sub: string;
  domain_id: string;
  domain_type: string;
  tg_id: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  metadata?: {
    file_name?: string;
    file_size?: number;
    file_type?: string;
    document_processing?: string;
    document_id?: string;
    biomarkers?: Biomarker[];
  };
}

export interface ChatSession {
  id: string;
  title: string | null;
  folder_id: string | null;
  created_at: string;
}

export interface ChatFolder {
  id: string;
  name: string;
  emoji?: string;
  color?: string;
  sort_order: number;
  created_at: string;
}

export interface ChatSearchResult {
  session_id: string;
  session_title: string | null;
  snippet?: string;
}

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface SSEEvent {
  token: string;
  done: boolean;
  message_id?: string;
  error?: string;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

// --- Documents (Epic 2) ---

export interface Document {
  id: string;
  original_filename: string;
  file_type: string;
  mime_type: string;
  file_size_bytes: number;
  processing_status: "uploaded" | "parsing" | "extracting" | "done" | "error";
  created_at: string;
}

export interface Biomarker {
  id: string;
  name: string;
  value: string;
  unit: string | null;
  ref_range_min: number | null;
  ref_range_max: number | null;
  ref_range_text: string | null;
  status: "normal" | "low" | "high" | "critical" | "unknown" | null;
  category: string | null;
}

export interface DocumentDetail extends Document {
  extracted_text: string | null;
  biomarkers: Biomarker[];
}
