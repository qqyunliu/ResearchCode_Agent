<script setup lang="ts">
import type { AgentReference } from "@/types/agent"

defineProps<{
  reference: AgentReference
  content: string
  loading: boolean
  error: string
}>()

defineEmits<{
  close: []
}>()
</script>

<template>
  <div
    class="backdrop"
    data-test="reference-dialog"
    role="presentation"
    @click.self="$emit('close')"
  >
    <article class="dialog" role="dialog" aria-modal="true" aria-label="Reference code">
      <header>
        <div>
          <span>{{ reference.entity_type }}</span>
          <h2>{{ reference.qualified_name }}</h2>
        </div>
        <button
          data-test="close-reference"
          type="button"
          aria-label="Close reference"
          @click="$emit('close')"
        >
          ×
        </button>
      </header>
      <p>{{ reference.file_path }}</p>
      <p>Lines {{ reference.start_line }}–{{ reference.end_line }}</p>
      <p v-if="loading" data-test="reference-loading">Loading indexed code…</p>
      <p v-else-if="error" class="error" data-test="reference-error">{{ error }}</p>
      <pre v-else><code>{{ content }}</code></pre>
    </article>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  z-index: 30;
  inset: 0;
  display: grid;
  padding: 24px;
  place-items: center;
  background: rgba(15, 23, 42, .55);
}
.dialog {
  width: min(860px, 100%);
  max-height: 85vh;
  padding: 24px;
  overflow: auto;
  border-radius: 20px;
  background: white;
  box-shadow: 0 24px 80px rgba(15, 23, 42, .28);
}
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
header span { color: #0f766e; font-size: .75rem; font-weight: 800; text-transform: uppercase; }
h2 { margin: 6px 0; color: #0f172a; }
p { color: #64748b; overflow-wrap: anywhere; }
button { border: 0; background: transparent; color: #475569; cursor: pointer; font-size: 1.8rem; }
pre { padding: 18px; overflow: auto; border-radius: 14px; background: #111827; color: #d1fae5; white-space: pre-wrap; }
.error { color: #be123c; }
</style>
