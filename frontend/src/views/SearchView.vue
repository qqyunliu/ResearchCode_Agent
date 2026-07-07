<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { hybridSearch } from "@/api/search"
import type { SearchHit } from "@/types/search"
import { projectIdFromQuery } from "@/utils/projectRoute"
import {
  clearSearchHistory,
  deleteSearchHistoryItem,
  loadSearchHistory,
  recordSearchHistory,
  type SearchHistoryItem,
} from "@/utils/searchHistory"

const projectId = ref(projectIdFromQuery(new URLSearchParams(window.location.search).get("project_id")))
const query = ref("")
const results = ref<SearchHit[]>([])
const loading = ref(false)
const searched = ref(false)
const errorMessage = ref("")
const history = ref<SearchHistoryItem[]>([])

const canSearch = computed(
  () => projectId.value > 0 && query.value.trim().length > 0 && !loading.value,
)
const visibleHistory = computed(() => history.value
  .slice()
  .sort((left, right) => {
    if (left.projectId === projectId.value && right.projectId !== projectId.value) return -1
    if (left.projectId !== projectId.value && right.projectId === projectId.value) return 1
    return 0
  })
  .slice(0, 8),
)

function refreshHistory() {
  history.value = loadSearchHistory()
}

async function fillFromHistory(item: SearchHistoryItem) {
  projectId.value = item.projectId
  query.value = item.query
  await search()
}

function removeHistoryItem(id: string) {
  history.value = deleteSearchHistoryItem(id)
}

function clearHistory() {
  clearSearchHistory()
  history.value = []
}

function formatHistoryTime(value: string) {
  const searchedAt = new Date(value).getTime()
  if (Number.isNaN(searchedAt)) return "时间未知"
  const diffMinutes = Math.max(0, Math.floor((Date.now() - searchedAt) / 60000))
  if (diffMinutes < 1) return "刚刚"
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours} 小时前`
  return new Date(value).toLocaleString()
}

async function search() {
  if (!canSearch.value) return
  loading.value = true
  errorMessage.value = ""
  try {
    results.value = await hybridSearch({
      project_id: projectId.value,
      query: query.value.trim(),
      limit: 10,
    })
    history.value = recordSearchHistory({
      projectId: projectId.value,
      query: query.value,
    })
  } catch {
    results.value = []
    errorMessage.value = "无法搜索，请确认后端服务和向量索引已就绪。"
  } finally {
    searched.value = true
    loading.value = false
  }
}

onMounted(refreshHistory)
</script>

<template>
  <main class="page">
    <header>
      <p class="eyebrow">混合检索</p>
      <h1>按语义和关键词查找代码</h1>
      <p>搜索已索引的代码实体，并查看源码位置与相关性得分。</p>
    </header>

    <form @submit.prevent="search">
      <label>
        项目 ID
        <input v-model.number="projectId" data-test="project-id" min="1" type="number" />
      </label>
      <label class="query">
        查询内容
        <input v-model="query" data-test="query" placeholder="例如：告警接口实现" type="search" />
      </label>
      <button data-test="search" :disabled="!canSearch">
        {{ loading ? "正在搜索……" : "搜索代码" }}
      </button>
    </form>

    <section v-if="visibleHistory.length > 0" class="history" data-test="search-history">
      <div class="history-head">
        <h2>历史搜索</h2>
        <button type="button" class="ghost" data-test="clear-history" @click="clearHistory">
          清空历史
        </button>
      </div>
      <ul>
        <li v-for="item in visibleHistory" :key="item.id">
          <button type="button" class="history-item" data-test="history-item" @click="fillFromHistory(item)">
            <strong>{{ item.query }}</strong>
            <span>项目 ID {{ item.projectId }} · {{ formatHistoryTime(item.searchedAt) }}</span>
          </button>
          <button
            type="button"
            class="delete-history"
            data-test="delete-history-item"
            aria-label="删除该条历史"
            @click.stop="removeHistoryItem(item.id)"
          >
            删除
          </button>
        </li>
      </ul>
    </section>

    <p v-if="errorMessage" class="notice error" data-test="error">{{ errorMessage }}</p>
    <p v-else-if="searched && !loading && results.length === 0" class="notice" data-test="empty">
      没有找到与该查询匹配的索引代码。
    </p>

    <section class="results">
      <article v-for="result in results" :key="result.entity_id" data-test="result">
        <div class="result-head">
          <span>{{ result.entity_type }}</span>
          <strong>{{ result.score.toFixed(3) }} · {{ result.source }}</strong>
        </div>
        <h2>{{ result.qualified_name }}</h2>
        <p>{{ result.file_path }} · {{ result.start_line }}–{{ result.end_line }}</p>
        <pre><code>{{ result.content }}</code></pre>
      </article>
    </section>
  </main>
</template>

<style scoped>
.page { max-width: 1180px; margin: 0 auto; padding: 48px 32px 72px; }
.eyebrow { color: #0f766e; font-size: .76rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1 { margin: 8px 0; color: #0f172a; font-size: clamp(2.2rem, 5vw, 4rem); letter-spacing: -.045em; }
header > p:last-child { color: #64748b; }
form { display: grid; grid-template-columns: 150px minmax(0, 1fr) auto; gap: 14px; margin-top: 30px; padding: 20px; border: 1px solid #dbe4ea; border-radius: 20px; background: white; }
label { display: grid; gap: 7px; color: #475569; font-size: .78rem; font-weight: 700; }
input { box-sizing: border-box; min-width: 0; width: 100%; padding: 12px 14px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
button { align-self: end; padding: 13px 20px; border: 0; border-radius: 10px; background: #0f766e; color: white; font-weight: 800; cursor: pointer; }
button:disabled { background: #94a3b8; cursor: not-allowed; }
.history { margin-top: 16px; padding: 18px 20px; border: 1px solid #dbe4ea; border-radius: 18px; background: white; }
.history-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.history h2 { margin: 0; color: #0f172a; font-size: 1rem; }
.history ul { display: grid; gap: 10px; margin: 14px 0 0; padding: 0; list-style: none; }
.history li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
.history-item { display: grid; gap: 4px; min-width: 0; padding: 10px 12px; border: 1px solid #dbe4ea; background: #f8fafc; color: #0f172a; text-align: left; }
.history-item strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item span { color: #64748b; font-size: .78rem; font-weight: 700; }
.ghost, .delete-history { padding: 8px 10px; background: #ecfeff; color: #0f766e; font-size: .78rem; }
.delete-history { background: #fff1f2; color: #be123c; }
.results { display: grid; gap: 14px; margin-top: 20px; }
.results article { padding: 20px; border: 1px solid #dbe4ea; border-radius: 18px; background: white; }
.result-head { display: flex; justify-content: space-between; color: #0f766e; font-size: .76rem; text-transform: uppercase; }
h2 { margin: 10px 0 4px; color: #0f172a; }
article p { color: #64748b; }
pre { padding: 14px; overflow: auto; border-radius: 12px; background: #111827; color: #d1fae5; white-space: pre-wrap; }
.notice { padding: 12px 16px; border-radius: 10px; background: #ecfeff; color: #155e75; }
.error { background: #fff1f2; color: #be123c; }
@media (max-width: 700px) { form, .history li { grid-template-columns: 1fr; } }
</style>
