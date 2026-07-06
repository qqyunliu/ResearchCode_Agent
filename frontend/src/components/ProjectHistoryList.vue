<script setup lang="ts">
import { computed, ref, watch } from "vue"
import type { Project } from "@/types/project"

const props = defineProps<{
  projects: Project[]
  selectedProjectId: number | null
  loading: boolean
}>()
defineEmits<{
  select: [id: number]
  refresh: []
  beginReorder: []
}>()

const search = ref("")
const sort = ref("manual")
const page = ref(1)
const pageSize = ref(10)
const filtered = computed(() => {
  const term = search.value.trim().toLowerCase()
  const items = props.projects.filter((item) =>
    !term || `${item.name} ${item.root_path}`.toLowerCase().includes(term))
  return [...items].sort((a, b) => {
    if (sort.value === "id") return a.id - b.id
    if (sort.value === "name") return a.name.localeCompare(b.name, "zh-CN")
    if (sort.value === "scan") return (b.last_scan_at || "").localeCompare(a.last_scan_at || "")
    return a.sort_order - b.sort_order
  })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
watch([search, sort, pageSize], () => { page.value = 1 })
</script>

<template>
  <section class="history-card">
    <div class="history-head"><h2>历史项目</h2><button data-test="refresh-projects" :disabled="loading" @click="$emit('refresh')">刷新</button></div>
    <input v-model="search" data-test="history-search" placeholder="搜索名称或路径" />
    <div class="filters">
      <select v-model="sort" aria-label="项目排序"><option value="manual">手动顺序</option><option value="id">项目 ID</option><option value="name">名称</option><option value="scan">最近扫描</option></select>
      <select v-model.number="pageSize" aria-label="每页数量"><option :value="5">5 / 页</option><option :value="10">10 / 页</option><option :value="20">20 / 页</option></select>
      <button data-test="begin-reorder" :disabled="projects.length < 2" @click="$emit('beginReorder')">调整顺序</button>
    </div>
    <p v-if="loading" class="state">正在加载项目……</p>
    <p v-else-if="!projects.length" class="state">还没有注册过项目。</p>
    <p v-else-if="!filtered.length" class="state">没有匹配的项目。</p>
    <button v-for="item in visible" :key="item.id" data-test="history-item" class="history-item" :class="{ selected: item.id === selectedProjectId }" @click="$emit('select', item.id)">
      <span><strong>{{ item.name }}</strong><small>ID {{ item.id }} · {{ item.status }}</small></span>
      <small :class="{ unavailable: !item.path_accessible }">{{ item.path_accessible ? "可访问" : "不可访问" }}</small>
      <small class="path" :title="item.root_path">{{ item.root_path }}</small>
    </button>
    <div v-if="pageCount > 1" class="pager"><button :disabled="page === 1" @click="page--">上一页</button><span>{{ page }} / {{ pageCount }}</span><button :disabled="page === pageCount" @click="page++">下一页</button></div>
  </section>
</template>

<style scoped>
.history-card{padding:18px;border:1px solid #dbe4ea;border-radius:18px;background:white}.history-head,.filters,.pager{display:flex;align-items:center;justify-content:space-between;gap:8px}.history-head{margin-bottom:14px}.history-head h2{margin:0}.filters{margin:12px 0;flex-wrap:wrap}input,select{box-sizing:border-box;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:9px}.filters select{width:auto}.history-item{display:grid;width:100%;gap:5px;margin:8px 0;padding:12px;text-align:left;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;color:#334155}.history-item span{display:flex;justify-content:space-between}.history-item.selected{border-color:#0f766e;background:#ecfdf5}.history-item small{color:#64748b}.history-item .unavailable{color:#be123c}.path{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.state{text-align:center;color:#64748b}.pager{justify-content:center;margin-top:12px}button{padding:8px 11px;border:0;border-radius:8px;cursor:pointer}button:disabled{cursor:not-allowed;opacity:.55}
</style>
