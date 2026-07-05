<script setup lang="ts">
import { computed, ref } from "vue"

import { searchChain } from "@/api/graph"
import GraphPanel from "@/components/GraphPanel.vue"
import type { GraphEdge, GraphNode } from "@/types/graph"

const projectId = ref(1)
const query = ref("")
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const selectedNode = ref<GraphNode | null>(null)
const loading = ref(false)
const errorMessage = ref("")
const hasSearched = ref(false)

const canSearch = computed(
  () => query.value.trim().length > 0 && !loading.value,
)

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
  } catch {
    nodes.value = []
    edges.value = []
    errorMessage.value = (
      "Unable to load the graph. Confirm the backend, project ID, "
      + "and vector index are available."
    )
  } finally {
    hasSearched.value = true
    loading.value = false
  }
}
</script>

<template>
  <main class="page-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">ResearchCode-Agent · GraphRAG</p>
        <h1>Trace code from request to implementation.</h1>
        <p class="subtitle">
          Search an indexed project, inspect its API chain, and open the exact
          code behind every node.
        </p>
      </div>
      <div class="status-pill">
        <span class="status-dot" />
        Week 3 graph explorer
      </div>
    </header>

    <form class="search-bar" @submit.prevent="submitSearch">
      <label>
        <span>Project</span>
        <input
          v-model.number="projectId"
          data-test="project-id"
          min="1"
          type="number"
        />
      </label>
      <label class="query-field">
        <span>Code or feature</span>
        <input
          v-model="query"
          data-test="query"
          placeholder="Where is the alert API implemented?"
          type="search"
        />
      </label>
      <button
        data-test="search"
        type="submit"
        :disabled="!canSearch"
      >
        {{ loading ? "Tracing…" : "Trace chain" }}
      </button>
    </form>

    <p v-if="errorMessage" class="notice error" data-test="error">
      {{ errorMessage }}
    </p>
    <p
      v-else-if="hasSearched && !loading && nodes.length === 0"
      class="notice"
      data-test="empty"
    >
      No connected code entities were found for this query.
    </p>

    <section class="workspace">
      <article class="graph-card">
        <div class="card-heading">
          <div>
            <p class="section-label">Relationship map</p>
            <h2>{{ nodes.length }} nodes · {{ edges.length }} edges</h2>
          </div>
          <div class="legend" aria-label="Graph legend">
            <span><i class="frontend" />Frontend</span>
            <span><i class="api" />API</span>
            <span><i class="method" />Method</span>
            <span><i class="klass" />Class</span>
          </div>
        </div>
        <div v-if="loading" class="graph-placeholder">Building graph…</div>
        <GraphPanel
          v-else-if="nodes.length"
          :nodes="nodes"
          :edges="edges"
          @select-node="selectedNode = $event"
        />
        <div v-else class="graph-placeholder">
          Run a search to reveal the code chain.
        </div>
      </article>

      <aside class="detail-card">
        <template v-if="selectedNode">
          <p class="section-label">Selected entity</p>
          <span class="type-chip">{{ selectedNode.entity_type }}</span>
          <h2>{{ selectedNode.qualified_name }}</h2>
          <dl>
            <div>
              <dt>File</dt>
              <dd>{{ selectedNode.file_path }}</dd>
            </div>
            <div>
              <dt>Lines</dt>
              <dd>{{ selectedNode.start_line }}–{{ selectedNode.end_line }}</dd>
            </div>
          </dl>
          <pre><code>{{ selectedNode.content }}</code></pre>
        </template>
        <template v-else>
          <p class="section-label">Entity inspector</p>
          <h2>Select a node</h2>
          <p class="detail-hint">
            Click any node to inspect its source path, line range, and indexed
            code.
          </p>
        </template>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.page-shell {
  max-width: 1480px;
  margin: 0 auto;
  padding: 52px 32px 72px;
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 32px;
  margin-bottom: 32px;
}

.eyebrow,
.section-label {
  margin: 0 0 8px;
  color: #0f766e;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1 {
  max-width: 780px;
  margin: 0;
  color: #0f172a;
  font-size: clamp(2.3rem, 5vw, 4.7rem);
  line-height: 0.98;
  letter-spacing: -0.055em;
}

.subtitle {
  max-width: 700px;
  margin: 22px 0 0;
  color: #64748b;
  font-size: 1.08rem;
  line-height: 1.65;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 14px;
  border: 1px solid #dbe4ea;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: #475569;
  font-size: 0.82rem;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.12);
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
  .hero {
    display: grid;
  }

  .status-pill {
    width: fit-content;
  }

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
  .page-shell {
    padding: 32px 16px 48px;
  }

  .search-bar {
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
