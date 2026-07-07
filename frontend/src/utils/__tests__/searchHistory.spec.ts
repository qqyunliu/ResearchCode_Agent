import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  clearSearchHistory,
  deleteSearchHistoryItem,
  getVisibleSearchHistory,
  loadSearchHistory,
  recordSearchHistory,
  SEARCH_HISTORY_KEY,
} from "../searchHistory"

describe("searchHistory", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-07T09:30:00Z"))
  })

  it("records a trimmed search and moves duplicate searches to the top", () => {
    recordSearchHistory({ projectId: 1, query: " alert API " })
    vi.setSystemTime(new Date("2026-07-07T09:35:00Z"))
    recordSearchHistory({ projectId: 2, query: "login controller" })
    recordSearchHistory({ projectId: 1, query: "alert API" })

    const history = loadSearchHistory()

    expect(history).toHaveLength(2)
    expect(history[0]).toMatchObject({ projectId: 1, query: "alert API" })
    expect(history[0].searchedAt).toBe("2026-07-07T09:35:00.000Z")
    expect(history[1]).toMatchObject({ projectId: 2, query: "login controller" })
  })

  it("keeps at most twenty records", () => {
    for (let index = 1; index <= 25; index += 1) {
      recordSearchHistory({ projectId: 1, query: `query ${index}` })
    }

    const history = loadSearchHistory()

    expect(history).toHaveLength(20)
    expect(history[0].query).toBe("query 25")
    expect(history.at(-1)?.query).toBe("query 6")
  })

  it("prioritizes the current project and returns at most eight visible records", () => {
    for (let index = 1; index <= 10; index += 1) {
      recordSearchHistory({
        projectId: index % 2 === 0 ? 2 : 1,
        query: `query ${index}`,
      })
    }

    const visible = getVisibleSearchHistory(1)

    expect(visible).toHaveLength(8)
    expect(visible.slice(0, 5).every((item) => item.projectId === 1)).toBe(true)
  })

  it("deletes one item and clears all history", () => {
    recordSearchHistory({ projectId: 1, query: "alert API" })
    recordSearchHistory({ projectId: 2, query: "login controller" })
    const [first] = loadSearchHistory()

    deleteSearchHistoryItem(first.id)

    expect(loadSearchHistory()).toHaveLength(1)
    clearSearchHistory()
    expect(loadSearchHistory()).toEqual([])
  })

  it("ignores broken localStorage data", () => {
    localStorage.setItem(SEARCH_HISTORY_KEY, "{not json")

    expect(loadSearchHistory()).toEqual([])
  })
})
