import axios from "axios"

import type {
  GraphResponse,
  SearchChainRequest,
} from "@/types/graph"

export async function searchChain(
  request: SearchChainRequest,
): Promise<GraphResponse> {
  const response = await axios.post<GraphResponse>(
    "/api/graph/search-chain",
    request,
  )
  return response.data
}
