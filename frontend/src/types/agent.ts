import type { GraphEdge, GraphNode } from "@/types/graph"

export type TaskType = "CODE_QA" | "TRACE_CHAIN" | "CHANGE_PLAN"
export type MessageRole = "user" | "assistant"

export interface AgentReference {
  citation: number
  entity_id: number
  file_path: string
  start_line: number
  end_line: number
  entity_type: string
  qualified_name: string
}

export interface AgentChatRequest {
  project_id: number
  question: string
  conversation_id?: number
  limit: number
}

export interface AgentChatResponse {
  conversation_id: number
  message_id: number
  task_type: TaskType
  answer: string
  references: AgentReference[]
  graph_nodes: GraphNode[]
  graph_edges: GraphEdge[]
  uncertainties: string[]
}

export interface AgentMessage {
  id: number
  role: MessageRole
  content: string
  task_type: TaskType | null
  references: AgentReference[]
  graph_nodes: GraphNode[]
  graph_edges: GraphEdge[]
  uncertainties: string[]
  created_at: string
}

export interface Conversation {
  id: number
  project_id: number
  title: string
  created_at: string
  updated_at: string
  messages: AgentMessage[]
}
