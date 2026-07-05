import axios from "axios"

import type {
  AgentChatRequest,
  AgentChatResponse,
  Conversation,
} from "@/types/agent"

export async function sendChat(
  data: AgentChatRequest,
): Promise<AgentChatResponse> {
  const response = await axios.post<AgentChatResponse>(
    "/api/agent/chat",
    data,
  )
  return response.data
}

export async function getConversation(
  conversationId: number,
  projectId: number,
): Promise<Conversation> {
  const response = await axios.get<Conversation>(
    `/api/agent/conversations/${conversationId}`,
    { params: { project_id: projectId } },
  )
  return response.data
}
