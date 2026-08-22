export interface BackendModel {
  key: string;
  label?: string;
  model: string;
  kind: string;
  location?: string;
}
export interface BackendModelsResponse { default: string; providers: BackendModel[]; }

export type DocumentKind = 'csv' | 'xlsx' | 'pdf' | 'json' | 'unknown';
export type DocumentStatus = 'parsed' | 'failed' | string;
export interface SourceRecord {
  title: string;
  abstract: string;
  authors: string[];
  year: number | null;
  venue: string;
  doi: string;
  full_text: string | null;
  raw: Record<string, unknown>;
}
export interface DocumentInfo {
  id: string; filename: string; content_type: string; kind: string; size_bytes: number;
  status: DocumentStatus; error: string; parsed_meta: { record_count?: number; records?: SourceRecord[]; [key:string]: unknown };
  created_at: string;
}
export type JobStatus = 'queued'|'running'|'succeeded'|'failed';
export interface JobInfo {
  id: string; kind: string; status: JobStatus; progress: number; error: string;
  result: Record<string, any>; created_at: string; updated_at: string;
}
export interface ReviewCreatePayload {
  topic: string;
  instructions?: string;
  provider?: string;
  records?: SourceRecord[];
  document_ids?: string[];
  orkg_query?: string;
  orkg_size?: number;
  max_tokens?: number;
}
export interface ReviewOut {
  id: string; job_id: string|null; topic: string; provider: string; model: string;
  content_md: string; structured: {
    sections?: Array<{heading:string; content:string}>;
    citations?: Array<{marker:string; source_index:number; title:string}>;
    sources?: Array<{index:number; title:string; authors:string[]; year:number|null; venue:string; doi:string}>;
    strategy?: string; provider?: string; model?: string; instructions?: string;
    usage?: {prompt_tokens?:number; completion_tokens?:number; total_tokens?:number};
    [key:string]: any;
  };
  csl_json: Array<Record<string, any>>;
  created_at: string;
}
export interface PreviewOut { id:string; format:string; html:string; }
export interface ReviewSummary { id:string; topic:string; provider:string; model:string; created_at:string; sections:number; }
export interface StreamDone { type:'done'; review_id:string; topic:string; provider:string; model:string; structured:ReviewOut['structured']; }
export interface ApiKeyInfo { id:string; name:string; prefix:string; revoked_at:string|null; last_used_at:string|null; created_at:string; }
export interface ApiKeyCreated extends ApiKeyInfo { api_key:string; }
export interface OrkgSearchResult { query:string; total:number; items:Array<Record<string,any>>; }
export interface OrkgAskResult { request:string; mode:'sparql'|'search'; count:number; records:Array<Record<string,any>>; sparql:string|null; sparql_error:string|null; columns:string[]; }
export interface SparqlResult { columns:string[]; rows:Array<Record<string,any>>; raw:Record<string,any>; }
export interface OrkgConnectResult { connected:boolean; expires_in:number; }
export interface ChatMessage {
  id:string; role:'user'|'assistant'|'system'; text:string; createdAt:number;
  status:'sent'|'error'; provider?:string; model?:string; review?:ReviewOut;
  documents?: Array<{id:string;name:string;kind:string;status:string;size:number}>;
}
export interface PendingDocument {
  id:string; file:File; name:string; kind:DocumentKind; size:number;
  status:'uploading'|'parsed'|'failed'; document?:DocumentInfo; error?:string;
}
export interface OrkgItemView { id?:string; title:string; abstract:string; year:number|null; doi:string; raw:Record<string,any>; }
