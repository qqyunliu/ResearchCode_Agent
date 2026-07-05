export interface GraphNode {
  entity_id: number
  label: string
  entity_type: string
  qualified_name: string
  file_path: string
  start_line: number
  end_line: number
  content: string
  metadata: Record<string, unknown>
}

export interface GraphEdge {
  relation_id: number
  source_id: number
  target_id: number
  relation_type: string
  confidence: number
  metadata: Record<string, unknown>
}

export interface GraphReference {
  citation: number
  entity_id: number
  file_path: string
  start_line: number
  end_line: number
  entity_type: string
  qualified_name: string
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  references: GraphReference[]
}

export interface SearchChainRequest {
  project_id: number
  query: string
  limit: number
  max_depth: number
}
