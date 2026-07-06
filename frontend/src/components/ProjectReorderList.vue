<script setup lang="ts">
import { ref, watch } from "vue"
const props = defineProps<{ projects: { id: number; name: string }[]; saving: boolean }>()
const emit = defineEmits<{ save: [ids: number[]]; cancel: [] }>()
const draft = ref([...props.projects])
const dragged = ref<number | null>(null)
watch(() => props.projects, (value) => { draft.value = [...value] })
function drop(target: number) {
  if (dragged.value === null || dragged.value === target) return
  const from = draft.value.findIndex((item) => item.id === dragged.value)
  const to = draft.value.findIndex((item) => item.id === target)
  const [item] = draft.value.splice(from, 1)
  draft.value.splice(to, 0, item)
}
</script>
<template>
  <section class="reorder">
    <h2>调整项目顺序</h2><p>拖动项目后保存，刷新页面仍会保留。</p>
    <div v-for="item in draft" :key="item.id" data-test="reorder-item" draggable="true" @dragstart="dragged=item.id" @dragover.prevent @drop="drop(item.id)">☰　{{ item.name }} <small>ID {{ item.id }}</small></div>
    <footer><button :disabled="saving" @click="emit('cancel')">取消</button><button data-test="save-order" :disabled="saving" @click="emit('save', draft.map(i=>i.id))">{{ saving ? "正在保存……" : "保存顺序" }}</button></footer>
  </section>
</template>
<style scoped>.reorder{padding:18px;border:1px solid #dbe4ea;border-radius:18px;background:white}.reorder div{margin:8px 0;padding:13px;border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc;cursor:grab}.reorder small{float:right;color:#64748b}footer{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}button{padding:10px 14px;border:0;border-radius:9px}</style>
