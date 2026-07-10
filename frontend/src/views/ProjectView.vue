<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import {
  buildVectorIndex, createProject, deleteProject, getFrontendRequestDiagnostics, getProjectStats,
  getVectorIndexStatus, listProjects, reorderProjects, scanProject,
} from "@/api/projects"
import ProjectDeleteDialog from "@/components/ProjectDeleteDialog.vue"
import ProjectHistoryList from "@/components/ProjectHistoryList.vue"
import ProjectReorderList from "@/components/ProjectReorderList.vue"
import type { FrontendRequestDiagnostics, Project, ProjectStats, VectorIndexSummary } from "@/types/project"

type Operation = "register" | "scan" | "index" | "reorder" | "delete" | null
const name = ref("")
const rootPath = ref("")
const projects = ref<Project[]>([])
const selectedProjectId = ref<number | null>(null)
const stats = ref<ProjectStats | null>(null)
const frontendDiagnostics = ref<FrontendRequestDiagnostics | null>(null)
const frontendDiagnosticsError = ref("")
const indexSummary = ref<VectorIndexSummary | null>(null)
const indexReady = ref(false)
const rebuildConfirmOpen = ref(false)
const operation = ref<Operation>(null)
const loadingProjects = ref(true)
const reorderMode = ref(false)
const deleteTarget = ref<Project | null>(null)
const deleteError = ref("")
const errorMessage = ref("")
let selectionToken = 0

const project = computed(() => projects.value.find((item) => item.id === selectedProjectId.value) ?? null)
const busy = computed(() => operation.value !== null)
const canRegister = computed(() => name.value.trim() && rootPath.value.trim() && !busy.value)

function normalizeCreated(value: Project): Project {
  return {
    ...value,
    created_at: value.created_at ?? new Date().toISOString(),
    last_scan_at: value.last_scan_at ?? null,
    sort_order: value.sort_order ?? 0,
    path_accessible: value.path_accessible ?? true,
  }
}

async function loadProjects(preserveId = selectedProjectId.value) {
  loadingProjects.value = true
  errorMessage.value = ""
  try {
    projects.value = await listProjects()
    const next = projects.value.some((item) => item.id === preserveId)
      ? preserveId : projects.value[0]?.id ?? null
    await selectProject(next)
  } catch {
    errorMessage.value = "无法加载历史项目，请确认后端服务可用。"
  } finally {
    loadingProjects.value = false
  }
}

async function selectProject(id: number | null) {
  selectedProjectId.value = id
  stats.value = null
  frontendDiagnostics.value = null
  frontendDiagnosticsError.value = ""
  indexSummary.value = null
  indexReady.value = false
  rebuildConfirmOpen.value = false
  errorMessage.value = ""
  const token = ++selectionToken
  const selected = projects.value.find((item) => item.id === id)
  if (!selected || selected.status !== "ready") return
  try {
    const [statsResult, indexStatus] = await Promise.all([
      getProjectStats(selected.id),
      getVectorIndexStatus(selected.id),
    ])
    if (token === selectionToken) {
      stats.value = statsResult
      indexReady.value = indexStatus.ready
    }
  } catch {
    if (token === selectionToken) errorMessage.value = "无法加载项目统计信息。"
  }
  void loadFrontendDiagnostics(selected.id, token)
}

async function loadFrontendDiagnostics(projectId: number, token = selectionToken) {
  try {
    const result = await getFrontendRequestDiagnostics(projectId, 10)
    if (token === selectionToken) frontendDiagnostics.value = result
  } catch {
    if (token === selectionToken) frontendDiagnosticsError.value = "前端请求诊断暂时不可用。"
  }
}

async function register() {
  if (!canRegister.value) return
  operation.value = "register"; errorMessage.value = ""
  try {
    const created = normalizeCreated(await createProject({ name: name.value.trim(), root_path: rootPath.value.trim() }))
    projects.value = [created, ...projects.value.map((item, index) => ({ ...item, sort_order: index + 1 }))]
    await selectProject(created.id)
    name.value = ""; rootPath.value = ""
  } catch (error: any) {
    if (error?.response?.data?.detail?.code === "PROJECT_ROOT_EXISTS") {
      await loadProjects()
      const existing = projects.value.find((item) => item.root_path.toLowerCase() === rootPath.value.trim().toLowerCase())
      if (existing) await selectProject(existing.id)
      errorMessage.value = "该路径已经注册，已定位到现有项目。"
    } else errorMessage.value = "无法注册项目，请检查项目路径和后端服务。"
  } finally { operation.value = null }
}

async function scan() {
  if (!project.value || busy.value || !project.value.path_accessible) return
  operation.value = "scan"; errorMessage.value = ""; indexSummary.value = null
  const id = project.value.id
  try {
    await scanProject(id)
    projects.value = projects.value.map((item) => item.id === id ? { ...item, status: "ready", last_scan_at: new Date().toISOString() } : item)
    stats.value = await getProjectStats(id)
    await loadFrontendDiagnostics(id)
  } catch { errorMessage.value = "无法扫描项目或加载统计信息。" }
  finally { operation.value = null }
}

async function buildIndex() {
  if (!project.value || project.value.status !== "ready" || busy.value) return
  operation.value = "index"; errorMessage.value = ""; indexSummary.value = null
  try {
    indexSummary.value = await buildVectorIndex(project.value.id)
    indexReady.value = true
    rebuildConfirmOpen.value = false
  }
  catch { errorMessage.value = "无法构建向量索引，请检查 Embedding 配置和向量存储是否可用。" }
  finally { operation.value = null }
}

function requestBuildIndex() {
  if (indexReady.value) rebuildConfirmOpen.value = true
  else void buildIndex()
}

async function saveOrder(ids: number[]) {
  operation.value = "reorder"; errorMessage.value = ""
  try { projects.value = await reorderProjects(ids); reorderMode.value = false }
  catch { reorderMode.value = false; await loadProjects(); errorMessage.value = "项目列表已发生变化，请重新调整顺序。" }
  finally { operation.value = null }
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  operation.value = "delete"; errorMessage.value = ""; deleteError.value = ""
  const deletedId = deleteTarget.value.id
  const index = projects.value.findIndex((item) => item.id === deletedId)
  try {
    await deleteProject(deletedId)
    projects.value.splice(index, 1)
    deleteTarget.value = null
    await selectProject(projects.value[index]?.id ?? projects.value[index - 1]?.id ?? null)
  } catch { deleteError.value = "无法删除项目，项目数据已保留，请稍后重试。" }
  finally { operation.value = null }
}

onMounted(() => loadProjects())
</script>

<template>
  <main class="page">
    <header><p class="eyebrow">项目工作区</p><h1>注册并分析代码库</h1><p>管理历史项目、扫描源码并构建检索索引。</p></header>
    <section class="register-panel">
      <form data-test="register-form" @submit.prevent="register">
        <label>项目名称<input v-model="name" data-test="project-name" placeholder="例如：告警平台" /></label>
        <label class="wide">绝对根路径<input v-model="rootPath" data-test="root-path" placeholder="F:/projects/alert-platform" /></label>
        <button data-test="register" :disabled="!canRegister">{{ operation === "register" ? "正在注册……" : "注册项目" }}</button>
      </form>
    </section>
    <p v-if="errorMessage" class="notice error" data-test="error">{{ errorMessage }}</p>

    <section class="workspace">
      <ProjectReorderList v-if="reorderMode" :projects="projects" :saving="operation === 'reorder'" @save="saveOrder" @cancel="reorderMode=false" />
      <ProjectHistoryList v-else :projects="projects" :selected-project-id="selectedProjectId" :loading="loadingProjects" @select="selectProject" @refresh="loadProjects()" @begin-reorder="reorderMode=true" />

      <section class="details">
        <div v-if="project">
          <span class="section-label">当前项目</span><h2>{{ project.name }}</h2>
          <p class="path" :title="project.root_path">{{ project.root_path }}</p>
          <div class="badges"><strong data-test="project-id">项目 ID {{ project.id }}</strong><span>{{ project.status }}</span><span :class="{ danger: !project.path_accessible }">{{ project.path_accessible ? "路径可访问" : "路径不可访问" }}</span></div>
          <p>最近扫描：{{ project.last_scan_at ? new Date(project.last_scan_at).toLocaleString() : "尚未扫描" }}</p>
          <div class="actions">
            <button data-test="scan" :disabled="busy || !project.path_accessible" @click="scan">{{ operation === "scan" ? "正在扫描……" : "扫描并刷新统计" }}</button>
            <button data-test="build-index" :disabled="busy || project.status !== 'ready'" @click="requestBuildIndex">{{ operation === "index" ? "正在构建索引……" : indexReady ? "重新构建向量索引" : "构建向量索引" }}</button>
            <button class="delete" @click="deleteError=''; deleteTarget=project">删除项目</button>
          </div>
          <nav class="shortcuts"><a :href="`/search?project_id=${project.id}`">代码搜索</a><a :href="`/graph?project_id=${project.id}`">关系图谱</a><a :href="`/chat?project_id=${project.id}`">Agent 对话</a></nav>
          <article v-if="indexSummary" class="index-result" data-test="index-result"><strong>向量索引已就绪</strong><span>已索引 {{ indexSummary.chunks_indexed }} 个代码块</span><span>集合：{{ indexSummary.collection_name }}</span></article>
          <section v-if="stats" class="stats" data-test="stats">
            <article><span>文件数</span><strong>{{ stats.total_files }}</strong></article><article><span>代码行数</span><strong>{{ stats.total_lines }}</strong></article><article><span>后端 API</span><strong>{{ stats.backend_api_count }}</strong></article><article><span>前端调用</span><strong>{{ stats.frontend_api_call_count }}</strong></article><article><span>跳过文件</span><strong>{{ stats.skipped_files }}</strong></article><article><span>解析错误</span><strong>{{ stats.parse_errors }}</strong></article>
          </section>
          <section v-if="frontendDiagnostics" class="frontend-diagnostics" data-test="frontend-diagnostics">
            <h3>前端请求诊断</h3>
            <div class="diagnostic-counts">
              <span>已识别 <strong>{{ frontendDiagnostics.identified_calls }}</strong></span>
              <span>已匹配 <strong>{{ frontendDiagnostics.matched_calls }}</strong></span>
              <span>未匹配 <strong>{{ frontendDiagnostics.unmatched_calls }}</strong></span>
              <span>未解析 <strong>{{ frontendDiagnostics.unresolved_candidates }}</strong></span>
            </div>
            <details v-if="frontendDiagnostics.unmatched_examples.length">
              <summary>未匹配示例</summary>
              <ul>
                <li v-for="item in frontendDiagnostics.unmatched_examples" :key="item.entity_id" data-test="unmatched-request">
                  {{ item.http_method }} {{ item.path }} - {{ item.file_path }}:{{ item.start_line }}
                </li>
              </ul>
            </details>
            <details v-if="frontendDiagnostics.unresolved_examples.length">
              <summary>未解析示例</summary>
              <ul>
                <li v-for="item in frontendDiagnostics.unresolved_examples" :key="`${item.file_path}:${item.reason}`" data-test="unresolved-request">
                  {{ item.file_path }} - {{ item.reason }}
                </li>
              </ul>
            </details>
          </section>
          <p v-else-if="frontendDiagnosticsError" class="diagnostics-error" data-test="frontend-diagnostics-error">{{ frontendDiagnosticsError }}</p>
        </div>
        <p v-else class="empty-detail">选择历史项目，或注册一个新项目开始分析。</p>
      </section>
    </section>
    <ProjectDeleteDialog v-if="deleteTarget" :project="deleteTarget" :deleting="operation === 'delete'" :error="deleteError" @confirm="confirmDelete" @cancel="deleteTarget=null" />
    <div v-if="rebuildConfirmOpen" class="modal-backdrop">
      <section data-test="rebuild-confirm" role="dialog" aria-modal="true">
        <h2>重新构建向量索引？</h2>
        <p>这会覆盖当前索引，重新为全部代码实体调用 Embedding API，并产生相应额度消耗。</p>
        <div class="actions"><button @click="rebuildConfirmOpen=false">取消</button><button data-test="confirm-rebuild" @click="buildIndex">确认重新构建</button></div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.page{max-width:1180px;margin:0 auto;padding:48px 32px 72px}.eyebrow,.section-label{color:#0f766e;font-size:.76rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}h1{margin:8px 0;color:#0f172a;font-size:clamp(2.2rem,5vw,4rem);letter-spacing:-.045em}header>p:last-child,.details p{color:#64748b}.register-panel{margin-top:30px;padding:20px;border:1px solid #dbe4ea;border-radius:20px;background:white}form{display:grid;grid-template-columns:220px minmax(0,1fr) auto;gap:14px}label{display:grid;gap:7px;color:#475569;font-size:.78rem;font-weight:700}input{box-sizing:border-box;min-width:0;width:100%;padding:12px 14px;border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc}button{padding:12px 16px;border:0;border-radius:10px;background:#0f766e;color:white;font-weight:700;cursor:pointer}form button{align-self:end;padding:13px 20px;font-weight:800}button:disabled{background:#94a3b8;cursor:not-allowed}.workspace{display:grid;grid-template-columns:370px minmax(0,1fr);gap:18px;margin-top:20px}.details{min-width:0;padding:22px;border:1px solid #dbe4ea;border-radius:18px;background:white}.details h2{margin:7px 0}.path{overflow-wrap:anywhere}.badges,.actions,.shortcuts,.index-result{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.badges span,.badges strong{padding:5px 9px;border-radius:8px;background:#ecfdf5;color:#0f766e}.badges .danger{background:#fff1f2;color:#be123c}.actions{margin:18px 0}.delete{background:#be123c}.shortcuts a{padding:9px 12px;border-radius:9px;background:#ecfeff;color:#0f766e;text-decoration:none;font-weight:700}.index-result{margin-top:15px;padding:14px;border-radius:12px;background:#ecfdf5;color:#166534}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}.stats article{display:grid;gap:6px;padding:14px;border:1px solid #e2e8f0;border-radius:12px}.stats span{color:#64748b;font-size:.76rem}.stats strong{font-size:1.5rem}.notice{margin:16px 0 0;padding:12px;border-radius:10px}.error{background:#fff1f2;color:#be123c}.empty-detail{display:grid;min-height:300px;place-items:center}.actions button{align-self:end}
@media(max-width:850px){form,.workspace{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.page{padding:32px 16px}.stats{grid-template-columns:1fr}}
.frontend-diagnostics{margin-top:22px;padding-top:18px;border-top:1px solid #e2e8f0}.frontend-diagnostics h3{margin:0 0 10px;font-size:1rem}.diagnostic-counts{display:flex;flex-wrap:wrap;gap:12px;color:#475569;font-size:.84rem}.diagnostic-counts strong{margin-left:4px;color:#0f172a}.frontend-diagnostics details{margin-top:10px;color:#475569;font-size:.84rem}.frontend-diagnostics summary{cursor:pointer;font-weight:700}.frontend-diagnostics ul{margin:7px 0 0;padding-left:18px;overflow-wrap:anywhere}.diagnostics-error{margin-top:18px;color:#a16207;font-size:.84rem}.modal-backdrop{position:fixed;inset:0;z-index:20;display:grid;place-items:center;padding:20px;background:#0f172a88}.modal-backdrop section{max-width:520px;padding:24px;border-radius:18px;background:white}.modal-backdrop .actions{justify-content:flex-end}
</style>
