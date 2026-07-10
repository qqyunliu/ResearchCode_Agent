import axios from "axios"
import { describe, expect, it, vi } from "vitest"

import { getFrontendRequestDiagnostics } from "../projects"

vi.mock("axios", () => ({
  default: { get: vi.fn() },
}))

const diagnostics = {
  project_id: 7,
  identified_calls: 44,
  matched_calls: 31,
  unmatched_calls: 13,
  unresolved_candidates: 2,
  unmatched_examples: [],
  unresolved_examples: [],
}

describe("projects API", () => {
  it("requests bounded frontend diagnostics for one project", async () => {
    vi.mocked(axios.get).mockResolvedValueOnce({ data: diagnostics })

    const result = await getFrontendRequestDiagnostics(7, 5)

    expect(axios.get).toHaveBeenCalledWith(
      "/api/projects/7/frontend-request-diagnostics",
      { params: { limit: 5 } },
    )
    expect(result.identified_calls).toBe(44)
  })
})
