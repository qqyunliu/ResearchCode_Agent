import { beforeEach, describe, expect, it } from "vitest"

import { loadSearchHistory, recordSearchHistory } from "../searchHistory"
import { GRAPH_HISTORY_KEY, loadGraphHistory, recordGraphHistory } from "../graphHistory"

describe("graphHistory", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("stores graph history separately from code search history", () => {
    recordSearchHistory({ projectId: 1, query: "code search" })
    recordGraphHistory({ projectId: 2, query: "graph search" })

    expect(loadSearchHistory()).toHaveLength(1)
    expect(loadSearchHistory()[0].query).toBe("code search")
    expect(loadGraphHistory()).toHaveLength(1)
    expect(loadGraphHistory()[0].query).toBe("graph search")
    expect(localStorage.getItem(GRAPH_HISTORY_KEY)).toContain("graph search")
  })
})
