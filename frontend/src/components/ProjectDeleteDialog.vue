<script setup lang="ts">
import { ref, watch } from "vue"
const props = defineProps<{ project: { id: number; name: string }; deleting: boolean; error?: string }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
const typedName = ref("")
watch(() => props.project.id, () => { typedName.value = "" })
</script>
<template>
  <div class="backdrop"><section role="dialog" aria-modal="true" aria-labelledby="delete-title">
    <h2 id="delete-title">删除项目“{{ project.name }}”</h2>
    <p>此操作不可恢复，将同步删除扫描文件、代码实体、关系、问题记录、对话和向量索引。</p>
    <p v-if="error" data-test="delete-error" class="error">{{ error }}</p>
    <label>输入完整项目名称以确认<input v-model="typedName" data-test="delete-name" /></label>
    <footer><button :disabled="deleting" @click="emit('cancel')">取消</button><button data-test="confirm-delete" class="danger" :disabled="deleting || typedName !== project.name" @click="emit('confirm')">{{ deleting ? "正在删除……" : "永久删除" }}</button></footer>
  </section></div>
</template>
<style scoped>.backdrop{position:fixed;inset:0;z-index:20;display:grid;place-items:center;padding:20px;background:#0f172a88}.backdrop section{max-width:520px;padding:24px;border-radius:18px;background:white}.backdrop input{box-sizing:border-box;width:100%;margin-top:8px;padding:11px;border:1px solid #cbd5e1;border-radius:9px}.error{padding:10px;border-radius:8px;background:#fff1f2;color:#be123c}footer{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}button{padding:10px 14px;border:0;border-radius:9px}.danger{background:#be123c;color:white}</style>
