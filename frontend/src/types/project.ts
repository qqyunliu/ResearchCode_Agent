export interface ProjectCreate {
  name: string
  root_path: string
}

export interface Project {
  id: number
  name: string
  root_path: string
  status: "created" | "scanning" | "ready" | "failed"
  created_at: string
  last_scan_at: string | null
  sort_order: number
  path_accessible: boolean
}

export interface ScanSummary {
  project_id: number
  status: "ready"
  files_indexed: number
  entities_indexed: number
  relations_indexed: number
  files_skipped: number
  parse_errors: number
}

export interface ProjectStats {
  project_id: number
  total_files: number
  total_lines: number
  languages: Record<string, number>
  entity_types: Record<string, number>
  relation_types: Record<string, number>
  backend_api_count: number
  frontend_api_call_count: number
  skipped_files: number
  parse_errors: number
  last_scan_at: string | null
}

export interface FrontendRequestExample {
  entity_id: number
  file_path: string
  start_line: number
  end_line: number
  http_method: string
  path: string
  resolution: string
}

export interface FrontendRequestWarningExample {
  file_path: string
  reason: string
  message: string
}

export interface FrontendRequestDiagnostics {
  project_id: number
  identified_calls: number
  matched_calls: number
  unmatched_calls: number
  unresolved_candidates: number
  unmatched_examples: FrontendRequestExample[]
  unresolved_examples: FrontendRequestWarningExample[]
}

export interface ProjectEntity {
  entity_id: number
  entity_type: string
  qualified_name: string
  file_path: string
  start_line: number
  end_line: number
  content: string
}

export interface VectorIndexSummary {
  project_id: number
  collection_name: string
  chunks_indexed: number
}

export interface VectorIndexStatus {
  project_id: number
  ready: boolean
}
