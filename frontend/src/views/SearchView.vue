<script setup lang="ts">
import { computed, ref } from "vue"

import { hybridSearch } from "@/api/search"
import type { SearchHit } from "@/types/search"

const projectId = ref(1)
const query = ref("")
const results = ref<SearchHit[]>([])
const loading = ref(false)
const searched = ref(false)
const errorMessage = ref("")

const canSearch = computed(
  () => projectId.value > 0 && query.value.trim().length > 0 && !loading.value,
)

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
  } catch {
    results.value = []
    errorMessage.value = "Unable to search. Confirm the backend and vector index are ready."
  } finally {
    searched.value = true
    loading.value = false
  }
}
</script>

<template>
  <main class="page">
    <header>
      <p class="eyebrow">Hybrid retrieval</p>
      <h1>Find code by meaning and keywords.</h1>
      <p>Search indexed entities and inspect their source location and score.</p>
    </header>

    <form @submit.prevent="search">
      <label>
        Project ID
        <input v-model.number="projectId" data-test="project-id" min="1" type="number" />
      </label>
      <label class="query">
        Query
        <input v-model="query" data-test="query" placeholder="alert controller" type="search" />
      </label>
      <button data-test="search" :disabled="!canSearch">
        {{ loading ? "Searching…" : "Search code" }}
      </button>
    </form>

    <p v-if="errorMessage" class="notice error" data-test="error">{{ errorMessage }}</p>
    <p v-else-if="searched && !loading && results.length === 0" class="notice" data-test="empty">
      No indexed code matched this query.
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
form { display: grid; grid-template-columns: 150px 1fr auto; gap: 14px; margin-top: 30px; padding: 20px; border: 1px solid #dbe4ea; border-radius: 20px; background: white; }
label { display: grid; gap: 7px; color: #475569; font-size: .78rem; font-weight: 700; }
input { padding: 12px 14px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
button { align-self: end; padding: 13px 20px; border: 0; border-radius: 10px; background: #0f766e; color: white; font-weight: 800; cursor: pointer; }
button:disabled { background: #94a3b8; cursor: not-allowed; }
.results { display: grid; gap: 14px; margin-top: 20px; }
.results article { padding: 20px; border: 1px solid #dbe4ea; border-radius: 18px; background: white; }
.result-head { display: flex; justify-content: space-between; color: #0f766e; font-size: .76rem; text-transform: uppercase; }
h2 { margin: 10px 0 4px; color: #0f172a; }
article p { color: #64748b; }
pre { padding: 14px; overflow: auto; border-radius: 12px; background: #111827; color: #d1fae5; white-space: pre-wrap; }
.notice { padding: 12px 16px; border-radius: 10px; background: #ecfeff; color: #155e75; }
.error { background: #fff1f2; color: #be123c; }
@media (max-width: 700px) { form { grid-template-columns: 1fr; } }
</style>
