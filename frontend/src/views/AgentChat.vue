<script setup lang="ts">
import { computed, ref } from "vue"

import { getConversation, sendChat } from "@/api/agent"
import { getProjectEntity } from "@/api/projects"
import GraphPanel from "@/components/GraphPanel.vue"
import ReferenceDialog from "@/components/ReferenceDialog.vue"
import type {
  AgentMessage,
  AgentReference,
} from "@/types/agent"

const demoQuestions = [
  "告警列表 API 在哪里实现？",
  "告警趋势数据的调用链是什么？",
  "设备状态页面使用了哪些后端 API？",
  "异常检测的入口函数在哪里？",
  "增加 risk_score 字段需要修改哪些文件？",
]

const projectId = ref(1)
const question = ref("")
const conversationId = ref<number | null>(null)
const restoreId = ref<number | null>(null)
const messages = ref<AgentMessage[]>([])
const loading = ref(false)
const errorMessage = ref("")
const selectedReference = ref<AgentReference | null>(null)
const referenceContent = ref("")
const referenceLoading = ref(false)
const referenceError = ref("")

const canSend = computed(
  () => projectId.value > 0 && question.value.trim().length > 0 && !loading.value,
)
const canRestore = computed(
  () => projectId.value > 0
    && restoreId.value !== null
    && restoreId.value > 0
    && !loading.value,
)

function userMessage(content: string): AgentMessage {
  return {
    id: -Date.now(),
    role: "user",
    content,
    task_type: null,
    references: [],
    graph_nodes: [],
    graph_edges: [],
    uncertainties: [],
    created_at: new Date().toISOString(),
  }
}

async function submit() {
  if (!canSend.value) return
  const currentQuestion = question.value.trim()
  loading.value = true
  errorMessage.value = ""
  try {
    const response = await sendChat({
      project_id: projectId.value,
      question: currentQuestion,
      ...(conversationId.value === null
        ? {}
        : { conversation_id: conversationId.value }),
      limit: 5,
    })
    conversationId.value = response.conversation_id
    messages.value.push(
      userMessage(currentQuestion),
      {
        id: response.message_id,
        role: "assistant",
        content: response.answer,
        task_type: response.task_type,
        references: response.references,
        graph_nodes: response.graph_nodes,
        graph_edges: response.graph_edges,
        uncertainties: response.uncertainties,
        created_at: new Date().toISOString(),
      },
    )
    question.value = ""
  } catch {
    errorMessage.value = (
      "无法获取 Agent 回答，请检查后端服务、项目、向量索引和 LLM 配置。"
    )
  } finally {
    loading.value = false
  }
}

async function restore() {
  if (!canRestore.value || restoreId.value === null) return
  loading.value = true
  errorMessage.value = ""
  try {
    const conversation = await getConversation(
      restoreId.value,
      projectId.value,
    )
    conversationId.value = conversation.id
    messages.value = conversation.messages
  } catch {
    errorMessage.value = "无法恢复该项目的指定会话。"
  } finally {
    loading.value = false
  }
}

async function openReference(reference: AgentReference) {
  selectedReference.value = reference
  referenceContent.value = ""
  referenceError.value = ""
  referenceLoading.value = true
  try {
    const entity = await getProjectEntity(
      projectId.value,
      reference.entity_id,
    )
    referenceContent.value = entity.content
  } catch {
    referenceError.value = "无法加载该引用对应的代码。"
  } finally {
    referenceLoading.value = false
  }
}
</script>

<template>
  <main class="page">
    <header class="hero">
      <div>
        <p class="eyebrow">统一代码 Agent</p>
        <h1 class="single-line-title">基于代码证据进行问答、追踪与规划</h1>
        <p>在一个会话中处理代码问答、调用链追踪和修改计划。</p>
      </div>
      <strong v-if="conversationId" class="conversation-chip">
        会话 {{ conversationId }}
      </strong>
    </header>

    <section class="controls">
      <label>
        项目 ID
        <input v-model.number="projectId" data-test="project-id" min="1" type="number" />
      </label>
      <label>
        恢复会话
        <input v-model.number="restoreId" data-test="restore-id" min="1" type="number" />
      </label>
      <button data-test="restore" type="button" :disabled="!canRestore" @click="restore">
        恢复
      </button>
    </section>

    <section class="demos" aria-label="示例问题">
      <button
        v-for="demo in demoQuestions"
        :key="demo"
        data-test="demo-question"
        type="button"
        @click="question = demo"
      >
        {{ demo }}
      </button>
    </section>

    <p v-if="errorMessage" class="notice error" data-test="error">{{ errorMessage }}</p>

    <section class="messages" aria-live="polite">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message"
        :class="message.role"
      >
        <div class="message-heading">
          <strong>{{ message.role === "user" ? "你" : "Agent" }}</strong>
          <span v-if="message.task_type">{{ message.task_type }}</span>
        </div>
        <p class="answer">{{ message.content }}</p>

        <p
          v-if="message.role === 'assistant'
            && message.references.length === 0
            && message.graph_nodes.length === 0"
          class="empty-evidence"
          data-test="empty-evidence"
        >
          此回答未附带已索引引用或图谱证据。
        </p>

        <div v-if="message.references.length" class="references">
          <button
            v-for="reference in message.references"
            :key="`${message.id}-${reference.entity_id}-${reference.citation}`"
            data-test="reference"
            type="button"
            @click="openReference(reference)"
          >
            <strong>{{ reference.file_path }}</strong>
            <span>
              {{ reference.entity_type }} ·
              {{ reference.start_line }}–{{ reference.end_line }}
            </span>
          </button>
        </div>

        <div v-if="message.uncertainties.length" class="uncertainties">
          <strong>不确定性</strong>
          <ul>
            <li v-for="item in message.uncertainties" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div v-if="message.graph_nodes.length" class="message-graph">
          <GraphPanel
            :nodes="message.graph_nodes"
            :edges="message.graph_edges"
          />
        </div>
      </article>
      <p v-if="messages.length === 0" class="welcome">
        选择一个示例问题，或针对已索引项目提问。
      </p>
    </section>

    <form class="composer" data-test="chat-form" @submit.prevent="submit">
      <input
        v-model="question"
        data-test="question"
        placeholder="询问代码位置、追踪调用链或规划修改……"
      />
      <button data-test="send" :disabled="!canSend">
        {{ loading ? "正在处理……" : "发送" }}
      </button>
    </form>

    <ReferenceDialog
      v-if="selectedReference"
      :reference="selectedReference"
      :content="referenceContent"
      :loading="referenceLoading"
      :error="referenceError"
      @close="selectedReference = null"
    />
  </main>
</template>

<style scoped>
.page { max-width: 1180px; margin: 0 auto; padding: 46px 32px 110px; }
.hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; }
.eyebrow { color: #0f766e; font-size: .76rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1 { max-width: 780px; margin: 8px 0; color: #0f172a; font-size: clamp(2.2rem, 5vw, 4rem); letter-spacing: -.05em; }
.single-line-title { max-width: none; font-size: clamp(2.2rem, 4vw, 3.4rem); white-space: nowrap; }
.hero p:last-child, .welcome { color: #64748b; }
.conversation-chip { padding: 9px 12px; border-radius: 999px; background: #ccfbf1; color: #115e59; white-space: nowrap; }
.controls { display: grid; grid-template-columns: 150px 190px auto; gap: 12px; margin-top: 28px; padding: 16px; border: 1px solid #dbe4ea; border-radius: 16px; background: white; }
label { display: grid; gap: 6px; color: #475569; font-size: .76rem; font-weight: 700; }
input { min-width: 0; padding: 12px 14px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
button { border: 0; cursor: pointer; font: inherit; }
.controls button, .composer button { align-self: end; padding: 12px 18px; border-radius: 10px; background: #0f766e; color: white; font-weight: 800; }
button:disabled { background: #94a3b8; cursor: not-allowed; }
.demos { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.demos button { padding: 8px 11px; border: 1px solid #cbd5e1; border-radius: 999px; background: white; color: #475569; font-size: .78rem; }
.messages { display: grid; gap: 14px; margin: 24px 0; }
.message { padding: 20px; border: 1px solid #dbe4ea; border-radius: 18px; background: white; }
.message.user { margin-left: min(18%, 160px); background: #ecfeff; }
.message-heading { display: flex; justify-content: space-between; color: #0f766e; font-size: .78rem; }
.answer { color: #334155; line-height: 1.7; white-space: pre-wrap; }
.references { display: grid; gap: 8px; margin-top: 14px; }
.references button { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border-radius: 10px; background: #f1f5f9; color: #334155; text-align: left; }
.references span { color: #64748b; font-size: .78rem; }
.uncertainties, .empty-evidence { margin-top: 14px; padding: 12px; border-radius: 10px; background: #fffbeb; color: #92400e; }
.uncertainties ul { margin-bottom: 0; }
.message-graph { margin-top: 16px; overflow: hidden; border-radius: 16px; }
.composer { position: sticky; bottom: 16px; display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 14px; border: 1px solid #dbe4ea; border-radius: 16px; background: rgba(255,255,255,.95); box-shadow: 0 16px 50px rgba(15,23,42,.14); }
.notice { padding: 12px; border-radius: 10px; }
.error { background: #fff1f2; color: #be123c; }
@media (max-width: 700px) { .hero, .references button { align-items: flex-start; flex-direction: column; } .single-line-title { white-space: normal; } .controls { grid-template-columns: 1fr; } .message.user { margin-left: 0; } }
</style>
