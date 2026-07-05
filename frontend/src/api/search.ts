import axios from "axios"

import type { HybridSearchRequest, SearchHit } from "@/types/search"

export async function hybridSearch(
  data: HybridSearchRequest,
): Promise<SearchHit[]> {
  const response = await axios.post<SearchHit[]>("/api/search/hybrid", data)
  return response.data
}
