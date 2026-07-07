<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { searchChain } from "@/api/graph"
import GraphPanel from "@/components/GraphPanel.vue"
import type { GraphEdge, GraphNode } from "@/types/graph"
import {
  clearGraphHistory,
  deleteGraphHistoryItem,
  loadGraphHistory,
  recordGraphHistory,
  type GraphHistoryItem,
} from "@/utils/graphHistory"
import { projectIdFromQuery } from "@/utils/projectRoute"

const projectId = ref(projectIdFromQuery(new URLSearchParams(window.location.search).get("project_id")))
const query = ref("")
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const selectedNode = ref<GraphNode | null>(null)
const loading = ref(false)
const errorMessage = ref("")
const hasSearched = ref(false)
const history = ref<GraphHistoryItem[]>([])

const canSearch = computed(
  () => query.value.trim().length > 0 && !loading.value,
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
  history.value = loadGraphHistory()
}

async function fillFromHistory(item: GraphHistoryItem) {
  projectId.value = item.projectId
  query.value = item.query
  await submitSearch()
}

function removeHistoryItem(id: string) {
  history.value = deleteGraphHistoryItem(id)
}

function clearHistory() {
  clearGraphHistory()
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

async function submitSearch() {
  if (!canSearch.value) {
    return
  }
  loading.value = true
  errorMessage.value = ""
  selectedNode.value = null
  try {
    const response = await searchChain({
      project_id: projectId.value,
      query: query.value.trim(),
      limit: 5,
      max_depth: 2,
    })
    nodes.value = response.nodes
    edges.value = response.edges
    history.value = recordGraphHistory({
      projectId: projectId.value,
      query: query.value,
    })
  } catch {
    nodes.value = []
    edges.value = []
    errorMessage.value = (
      "无法加载关系图谱，请确认后端服务、项目 ID 和向量索引可用。"
    )
  } finally {
    hasSearched.value = true
    loading.value = false
  }
}

onMounted(refreshHistory)
</script>

<template>
  <main class="page">
    <header class="hero">
      <div>
        <p class="eyebrow">GraphRAG</p>
        <h1>从请求追踪到代码实现</h1>
        <p class="subtitle">
          搜索已索引项目，查看 API 调用链，并打开每个节点对应的源码。
        </p>
      </div>
    </header>

    <form class="search-bar" @submit.prevent="submitSearch">
      <label>
        <span>项目 ID</span>
        <input
          v-model.number="projectId"
          data-test="project-id"
          min="1"
          type="number"
        />
      </label>
      <label class="query-field">
        <span>代码或功能</span>
        <input
          v-model="query"
          data-test="query"
          placeholder="例如：告警 API 在哪里实现？"
          type="search"
        />
      </label>
      <button
        data-test="search"
        type="submit"
        :disabled="!canSearch"
      >
        {{ loading ? "正在追踪……" : "追踪调用链" }}
      </button>
    </form>

    <section v-if="visibleHistory.length > 0" class="history" data-test="graph-history">
      <div class="history-head">
        <h2>历史记录</h2>
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

    <p v-if="errorMessage" class="notice error" data-test="error">
      {{ errorMessage }}
    </p>
    <p
      v-else-if="hasSearched && !loading && nodes.length === 0"
      class="notice"
      data-test="empty"
    >
      没有找到与该查询关联的代码实体。
    </p>

    <section class="workspace">
      <article class="graph-card">
        <div class="card-heading">
          <div>
            <p class="section-label">关系图</p>
            <h2>{{ nodes.length }} 个节点 · {{ edges.length }} 条边</h2>
          </div>
          <div class="legend" aria-label="图谱图例">
            <span><i class="frontend" />前端</span>
            <span><i class="api" />API</span>
            <span><i class="method" />方法</span>
            <span><i class="klass" />类</span>
          </div>
        </div>
        <div v-if="loading" class="graph-placeholder">正在构建图谱……</div>
        <GraphPanel
          v-else-if="nodes.length"
          :nodes="nodes"
          :edges="edges"
          @select-node="selectedNode = $event"
        />
        <div v-else class="graph-placeholder">
          运行搜索以展示代码调用链。
        </div>
      </article>

      <aside class="detail-card">
        <template v-if="selectedNode">
          <p class="section-label">已选实体</p>
          <span class="type-chip">{{ selectedNode.entity_type }}</span>
          <h2>{{ selectedNode.qualified_name }}</h2>
          <dl>
            <div>
              <dt>文件</dt>
              <dd>{{ selectedNode.file_path }}</dd>
            </div>
            <div>
              <dt>行号</dt>
              <dd>{{ selectedNode.start_line }}–{{ selectedNode.end_line }}</dd>
            </div>
          </dl>
          <pre><code>{{ selectedNode.content }}</code></pre>
        </template>
        <template v-else>
          <p class="section-label">实体详情</p>
          <h2>请选择节点</h2>
          <p class="detail-hint">
            点击任意节点，查看其源码路径、行号范围和已索引代码。
          </p>
        </template>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 48px 32px 72px;
}

.hero {
  margin-bottom: 30px;
}

.eyebrow {
  color: #0f766e;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.section-label {
  margin: 0 0 8px;
  color: #0f766e;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1 {
  margin: 8px 0;
  color: #0f172a;
  font-size: clamp(2.2rem, 5vw, 4rem);
  letter-spacing: -0.045em;
}

.subtitle {
  max-width: 700px;
  color: #64748b;
}

.search-bar {
  display: grid;
  grid-template-columns: 150px minmax(260px, 1fr) auto;
  gap: 14px;
  padding: 18px;
  border: 1px solid #dbe4ea;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.07);
}

label {
  display: grid;
  gap: 7px;
  color: #475569;
  font-size: 0.76rem;
  font-weight: 700;
}

input {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 11px;
  background: #f8fafc;
  color: #0f172a;
  font: inherit;
  outline: none;
}

input:focus {
  border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.1);
}

button {
  align-self: end;
  padding: 13px 22px;
  border: 0;
  border-radius: 11px;
  background: #0f766e;
  color: white;
  font-weight: 800;
  cursor: pointer;
}

button:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.history {
  margin-top: 16px;
  padding: 18px 20px;
  border: 1px solid #dbe4ea;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.88);
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history h2 {
  margin: 0;
  color: #0f172a;
  font-size: 1rem;
}

.history ul {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.history li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.history-item {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #dbe4ea;
  background: #f8fafc;
  color: #0f172a;
  text-align: left;
}

.history-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item span {
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 700;
}

.ghost,
.delete-history {
  padding: 8px 10px;
  background: #ecfeff;
  color: #0f766e;
  font-size: 0.78rem;
}

.delete-history {
  background: #fff1f2;
  color: #be123c;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 20px;
  margin-top: 20px;
}

.graph-card,
.detail-card {
  border: 1px solid #dbe4ea;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.06);
}

.graph-card {
  min-width: 0;
  padding: 20px;
}

.detail-card {
  padding: 24px;
  overflow: hidden;
}

.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
}

h2 {
  margin: 0;
  color: #172033;
  font-size: 1.15rem;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  color: #64748b;
  font-size: 0.72rem;
}

.legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}

.legend i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.frontend { background: #8b5cf6; }
.api { background: #0ea5e9; }
.method { background: #10b981; }
.klass { background: #f59e0b; }

.graph-placeholder {
  display: grid;
  min-height: 560px;
  place-items: center;
  border-radius: 20px;
  background: #f8fafc;
  color: #94a3b8;
}

.notice {
  margin: 16px 0 0;
  padding: 12px 16px;
  border-radius: 12px;
  background: #ecfeff;
  color: #155e75;
}

.notice.error {
  background: #fff1f2;
  color: #be123c;
}

.type-chip {
  display: inline-block;
  margin: 4px 0 12px;
  padding: 5px 9px;
  border-radius: 7px;
  background: #ccfbf1;
  color: #115e59;
  font: 700 0.72rem/1 monospace;
}

dl {
  display: grid;
  gap: 12px;
  margin: 24px 0;
}

dl div {
  display: grid;
  gap: 4px;
}

dt {
  color: #94a3b8;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: #334155;
  font-size: 0.88rem;
}

pre {
  max-height: 400px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 14px;
  background: #111827;
  color: #d1fae5;
  font-size: 0.78rem;
  line-height: 1.6;
  white-space: pre-wrap;
}

.detail-hint {
  color: #64748b;
  line-height: 1.65;
}

@media (max-width: 980px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .search-bar {
    grid-template-columns: 120px 1fr;
  }

  .search-bar button {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .page {
    padding: 32px 16px 48px;
  }

  .search-bar,
  .history li {
    grid-template-columns: 1fr;
  }

  .card-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .legend {
    justify-content: flex-start;
  }
}
</style>
