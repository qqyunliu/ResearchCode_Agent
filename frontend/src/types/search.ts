export interface HybridSearchRequest {
  project_id: number
  query: string
  limit: number
}

export interface SearchHit {
  entity_id: number
  entity_type: string
  name: string
  qualified_name: string
  file_path: string
  start_line: number
  end_line: number
  content: string
  metadata: Record<string, unknown>
  score: number
  source: string
}
