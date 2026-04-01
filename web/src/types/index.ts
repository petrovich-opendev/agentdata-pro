export interface User {
  sub: string;
  domain_id: string;
  domain_type: string;
  tg_id: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
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
