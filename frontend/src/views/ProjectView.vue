<script setup lang="ts">
import { computed, ref } from "vue"

import {
  buildVectorIndex,
  createProject,
  getProjectStats,
  scanProject,
} from "@/api/projects"
import type {
  Project,
  ProjectStats,
  VectorIndexSummary,
} from "@/types/project"

type ProjectOperation = "register" | "scan" | "index" | null

const name = ref("")
const rootPath = ref("")
const project = ref<Project | null>(null)
const stats = ref<ProjectStats | null>(null)
const activeOperation = ref<ProjectOperation>(null)
const scanCompleted = ref(false)
const indexSummary = ref<VectorIndexSummary | null>(null)
const errorMessage = ref("")
const busy = computed(() => activeOperation.value !== null)

const canRegister = computed(
  () => name.value.trim().length > 0
    && rootPath.value.trim().length > 0
    && !busy.value,
)

async function register() {
  if (!canRegister.value) return
  activeOperation.value = "register"
  errorMessage.value = ""
  try {
    project.value = await createProject({
      name: name.value.trim(),
      root_path: rootPath.value.trim(),
    })
    stats.value = null
    scanCompleted.value = false
    indexSummary.value = null
  } catch {
    errorMessage.value = "Unable to register the project. Check the path and backend."
  } finally {
    activeOperation.value = null
  }
}

async function scan() {
  if (!project.value || busy.value) return
  activeOperation.value = "scan"
  errorMessage.value = ""
  indexSummary.value = null
  try {
    await scanProject(project.value.id)
    stats.value = await getProjectStats(project.value.id)
    scanCompleted.value = true
  } catch {
    scanCompleted.value = false
    errorMessage.value = "Unable to scan the project or load its statistics."
  } finally {
    activeOperation.value = null
  }
}

async function buildIndex() {
  if (!project.value || !scanCompleted.value || busy.value) return
  activeOperation.value = "index"
  errorMessage.value = ""
  indexSummary.value = null
  try {
    indexSummary.value = await buildVectorIndex(project.value.id)
  } catch {
    errorMessage.value = (
      "Unable to build the vector index. Confirm the embedding "
      + "configuration and vector store are available."
    )
  } finally {
    activeOperation.value = null
  }
}
</script>

<template>
  <main class="page">
    <header>
      <p class="eyebrow">Project workspace</p>
      <h1>Register and inspect a codebase.</h1>
      <p>Store an absolute source path, scan its files, and review indexed totals.</p>
    </header>

    <section class="panel">
      <form data-test="register-form" @submit.prevent="register">
        <label>
          Project name
          <input
            v-model="name"
            data-test="project-name"
            placeholder="Alert platform"
          />
        </label>
        <label class="wide">
          Absolute root path
          <input
            v-model="rootPath"
            data-test="root-path"
            placeholder="F:/projects/alert-platform"
          />
        </label>
        <button data-test="register" :disabled="!canRegister">
          {{ activeOperation === "register" ? "Registering…" : "Register project" }}
        </button>
      </form>

      <p v-if="errorMessage" class="notice error" data-test="error">
        {{ errorMessage }}
      </p>

      <article v-if="project" class="project-card">
        <div>
          <span>Registered project</span>
          <h2>{{ project.name }}</h2>
          <p>{{ project.root_path }}</p>
          <strong data-test="project-id">Project ID {{ project.id }}</strong>
        </div>
        <div class="project-actions">
          <button data-test="scan" :disabled="busy" @click="scan">
            {{ activeOperation === "scan" ? "Scanning…" : "Scan and refresh stats" }}
          </button>
          <button
            data-test="build-index"
            :disabled="busy || !scanCompleted"
            @click="buildIndex"
          >
            {{ activeOperation === "index" ? "Building index…" : "Build vector index" }}
          </button>
        </div>
      </article>
      <article
        v-if="indexSummary"
        class="index-result"
        data-test="index-result"
      >
        <strong>Vector index ready</strong>
        <span>{{ indexSummary.chunks_indexed }} chunks indexed</span>
        <span>Collection: {{ indexSummary.collection_name }}</span>
      </article>
    </section>

    <section v-if="stats" class="stats" data-test="stats">
      <article><span>Files</span><strong>{{ stats.total_files }}</strong></article>
      <article><span>Lines</span><strong>{{ stats.total_lines }}</strong></article>
      <article><span>Backend APIs</span><strong>{{ stats.backend_api_count }}</strong></article>
      <article><span>Frontend calls</span><strong>{{ stats.frontend_api_call_count }}</strong></article>
      <article><span>Skipped</span><strong>{{ stats.skipped_files }}</strong></article>
      <article><span>Parse errors</span><strong>{{ stats.parse_errors }}</strong></article>
    </section>
  </main>
</template>

<style scoped>
.page { max-width: 1180px; margin: 0 auto; padding: 48px 32px 72px; }
.eyebrow { color: #0f766e; font-size: .76rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1 { margin: 8px 0; color: #0f172a; font-size: clamp(2.2rem, 5vw, 4rem); letter-spacing: -.045em; }
header > p:last-child, .project-card p { color: #64748b; }
.panel { margin-top: 30px; padding: 22px; border: 1px solid #dbe4ea; border-radius: 22px; background: rgba(255,255,255,.9); }
form { display: grid; grid-template-columns: 220px 1fr auto; gap: 14px; }
label { display: grid; gap: 7px; color: #475569; font-size: .78rem; font-weight: 700; }
input { padding: 12px 14px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
button { align-self: end; padding: 13px 18px; border: 0; border-radius: 10px; background: #0f766e; color: white; font-weight: 800; cursor: pointer; }
button:disabled { background: #94a3b8; cursor: not-allowed; }
.project-card { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 20px; padding: 18px; border-radius: 16px; background: #f8fafc; }
.project-card span, .stats span { color: #64748b; font-size: .76rem; font-weight: 700; text-transform: uppercase; }
.project-card h2 { margin: 6px 0; }
.project-card strong { color: #0f766e; }
.project-actions { display: flex; align-items: center; gap: 10px; }
.index-result { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 14px; padding: 14px 18px; border-radius: 14px; background: #ecfdf5; color: #166534; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 20px; }
.stats article { display: grid; gap: 8px; padding: 20px; border: 1px solid #dbe4ea; border-radius: 16px; background: white; }
.stats strong { color: #0f172a; font-size: 1.8rem; }
.notice { margin: 16px 0 0; padding: 12px; border-radius: 10px; }
.error { background: #fff1f2; color: #be123c; }
@media (max-width: 760px) { form, .stats { grid-template-columns: 1fr; } .project-card { align-items: flex-start; flex-direction: column; } .project-actions { align-items: stretch; flex-direction: column; width: 100%; } }
</style>
