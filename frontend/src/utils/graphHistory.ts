import {
  createLocalHistoryStore,
  type SearchHistoryInput,
  type SearchHistoryItem,
} from "./searchHistory"

export type GraphHistoryItem = SearchHistoryItem
export type GraphHistoryInput = SearchHistoryInput

export const GRAPH_HISTORY_KEY = "research-code-agent:graph-history"

const graphHistoryStore = createLocalHistoryStore(GRAPH_HISTORY_KEY)

export const loadGraphHistory = graphHistoryStore.load
export const recordGraphHistory = graphHistoryStore.record
export const getVisibleGraphHistory = graphHistoryStore.visible
export const deleteGraphHistoryItem = graphHistoryStore.deleteItem
export const clearGraphHistory = graphHistoryStore.clear
