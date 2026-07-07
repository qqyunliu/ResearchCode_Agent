export interface SearchHistoryItem {
  id: string
  projectId: number
  query: string
  searchedAt: string
}

export interface SearchHistoryInput {
  projectId: number
  query: string
}

export const SEARCH_HISTORY_KEY = "research-code-agent:search-history"

const MAX_HISTORY_ITEMS = 20
const MAX_VISIBLE_ITEMS = 8

function isSearchHistoryItem(value: unknown): value is SearchHistoryItem {
  if (!value || typeof value !== "object") return false
  const item = value as Record<string, unknown>
  return (
    typeof item.id === "string" &&
    typeof item.projectId === "number" &&
    Number.isSafeInteger(item.projectId) &&
    item.projectId > 0 &&
    typeof item.query === "string" &&
    item.query.trim().length > 0 &&
    typeof item.searchedAt === "string"
  )
}

function saveSearchHistory(storageKey: string, items: SearchHistoryItem[]) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(items))
  } catch {
    // Search history is a convenience feature; storage failures should not break search.
  }
}

function itemId(projectId: number, query: string) {
  return `${projectId}:${query.trim().toLowerCase()}`
}

export function createLocalHistoryStore(storageKey: string) {
  function load(): SearchHistoryItem[] {
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.filter(isSearchHistoryItem).slice(0, MAX_HISTORY_ITEMS)
    } catch {
      return []
    }
  }

  function record(input: SearchHistoryInput): SearchHistoryItem[] {
    const query = input.query.trim()
    if (!Number.isSafeInteger(input.projectId) || input.projectId <= 0 || !query) {
      return load()
    }
    const id = itemId(input.projectId, query)
    const next: SearchHistoryItem = {
      id,
      projectId: input.projectId,
      query,
      searchedAt: new Date().toISOString(),
    }
    const history = load().filter((item) => item.id !== id)
    const updated = [next, ...history].slice(0, MAX_HISTORY_ITEMS)
    saveSearchHistory(storageKey, updated)
    return updated
  }

  function visible(projectId: number): SearchHistoryItem[] {
    return load()
      .slice()
      .sort((left, right) => {
        if (left.projectId === projectId && right.projectId !== projectId) return -1
        if (left.projectId !== projectId && right.projectId === projectId) return 1
        return 0
      })
      .slice(0, MAX_VISIBLE_ITEMS)
  }

  function deleteItem(id: string): SearchHistoryItem[] {
    const updated = load().filter((item) => item.id !== id)
    saveSearchHistory(storageKey, updated)
    return updated
  }

  function clear() {
    try {
      localStorage.removeItem(storageKey)
    } catch {
      // Ignore browser storage failures.
    }
  }

  return { load, record, visible, deleteItem, clear }
}

const searchHistoryStore = createLocalHistoryStore(SEARCH_HISTORY_KEY)

export const loadSearchHistory = searchHistoryStore.load
export const recordSearchHistory = searchHistoryStore.record
export const getVisibleSearchHistory = searchHistoryStore.visible
export const deleteSearchHistoryItem = searchHistoryStore.deleteItem
export const clearSearchHistory = searchHistoryStore.clear
