import { flushPromises, mount } from "@vue/test-utils"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AgentChat from "../AgentChat.vue"

const api = vi.hoisted(() => ({
  getConversation: vi.fn(),
  getProjectEntity: vi.fn(),
  sendChat: vi.fn(),
}))
vi.mock("@/api/agent", () => ({
  getConversation: api.getConversation,
  sendChat: api.sendChat,
}))
vi.mock("@/api/projects", () => ({
  getProjectEntity: api.getProjectEntity,
}))

const reference = {
  citation: 1,
  entity_id: 5,
  file_path: "backend/src/AlertController.java",
  start_line: 10,
  end_line: 13,
  entity_type: "java_method",
  qualified_name: "AlertController.getAlert",
}

const graphNode = {
  entity_id: 5,
  label: "AlertController.getAlert",
  entity_type: "java_method",
  qualified_name: "AlertController.getAlert",
  file_path: reference.file_path,
  start_line: 10,
  end_line: 13,
  content: "return alertService.find();",
  metadata: {},
}

const response = {
  conversation_id: 9,
  message_id: 20,
  task_type: "TRACE_CHAIN",
  answer: "The frontend calls AlertController [1].",
  references: [reference],
  graph_nodes: [graphNode],
  graph_edges: [],
  uncertainties: ["Service implementation needs confirmation."],
}

const GraphPanelStub = defineComponent({
  props: ["nodes", "edges"],
  template: '<div data-test="graph-stub">{{ nodes.length }}</div>',
})

function mountChat() {
  return mount(AgentChat, {
    global: {
      stubs: {
        GraphPanel: GraphPanelStub,
      },
    },
  })
}

async function submit(wrapper: ReturnType<typeof mountChat>, question: string) {
  await wrapper.get('[data-test="question"]').setValue(question)
  await wrapper.get('[data-test="chat-form"]').trigger("submit")
  await flushPromises()
}

describe("AgentChat", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders Chinese Agent copy and demo questions", () => {
    const wrapper = mountChat()

    const title = wrapper.get("h1")
    expect(title.text()).toBe("基于代码证据进行问答、追踪与规划")
    expect(title.classes()).toContain("single-line-title")
    expect(wrapper.text()).toContain("恢复会话")
    expect(wrapper.get('[data-test="send"]').text()).toContain("发送")
    expect(wrapper.findAll('[data-test="demo-question"]')[0].text())
      .toContain("告警列表 API")
  })

  it("disables blank submission and provides five demo questions", async () => {
    const wrapper = mountChat()
    expect(wrapper.get('[data-test="send"]').attributes("disabled"))
      .toBeDefined()
    const demos = wrapper.findAll('[data-test="demo-question"]')
    expect(demos).toHaveLength(5)

    await demos[0].trigger("click")
    expect(
      (wrapper.get('[data-test="question"]').element as HTMLInputElement)
        .value,
    ).not.toBe("")
  })

  it("omits conversation ID on first request and uses it later", async () => {
    api.sendChat.mockResolvedValue(response)
    const wrapper = mountChat()
    await submit(wrapper, "Trace the alert flow")

    expect(api.sendChat).toHaveBeenNthCalledWith(1, {
      project_id: 1,
      question: "Trace the alert flow",
      limit: 5,
    })
    await submit(wrapper, "Where is the service?")
    expect(api.sendChat).toHaveBeenNthCalledWith(2, {
      project_id: 1,
      question: "Where is the service?",
      conversation_id: 9,
      limit: 5,
    })
  })

  it("renders task, answer, references, graph, and uncertainties", async () => {
    api.sendChat.mockResolvedValue(response)
    const wrapper = mountChat()
    await submit(wrapper, "Trace the alert flow")

    expect(wrapper.text()).toContain("TRACE_CHAIN")
    expect(wrapper.text()).toContain("The frontend calls AlertController")
    expect(wrapper.text()).toContain("backend/src/AlertController.java")
    expect(wrapper.text()).toContain("10–13")
    expect(wrapper.get('[data-test="graph-stub"]').text()).toBe("1")
    expect(wrapper.text()).toContain(
      "Service implementation needs confirmation",
    )
  })

  it("loads exact entity code when a reference is clicked", async () => {
    api.sendChat.mockResolvedValue(response)
    api.getProjectEntity.mockResolvedValue({
      ...graphNode,
      content: "return alertService.find();",
    })
    const wrapper = mountChat()
    await submit(wrapper, "Trace the alert flow")
    await wrapper.get('[data-test="reference"]').trigger("click")
    await flushPromises()

    expect(api.getProjectEntity).toHaveBeenCalledWith(1, 5)
    expect(wrapper.get('[data-test="reference-dialog"]').text()).toContain(
      "return alertService.find()",
    )
  })

  it("shows API errors and empty evidence", async () => {
    api.sendChat.mockRejectedValueOnce(new Error("offline"))
    const wrapper = mountChat()
    await submit(wrapper, "Question")
    expect(wrapper.get('[data-test="error"]').text()).toContain(
      "无法获取 Agent 回答",
    )

    api.sendChat.mockResolvedValueOnce({
      ...response,
      answer: "No supporting code evidence was found.",
      references: [],
      graph_nodes: [],
      uncertainties: [],
    })
    await submit(wrapper, "Missing")
    expect(wrapper.find('[data-test="empty-evidence"]').exists()).toBe(true)
  })

  it("restores messages without adding history to the next request", async () => {
    api.getConversation.mockResolvedValue({
      id: 12,
      project_id: 1,
      title: "Saved",
      created_at: "2026-07-05T12:00:00Z",
      updated_at: "2026-07-05T12:01:00Z",
      messages: [
        {
          id: 1,
          role: "user",
          content: "Historical question",
          task_type: null,
          references: [],
          graph_nodes: [],
          graph_edges: [],
          uncertainties: [],
          created_at: "2026-07-05T12:00:00Z",
        },
        {
          id: 2,
          role: "assistant",
          content: "Historical answer",
          task_type: "CODE_QA",
          references: [],
          graph_nodes: [],
          graph_edges: [],
          uncertainties: [],
          created_at: "2026-07-05T12:00:01Z",
        },
      ],
    })
    api.sendChat.mockResolvedValue({ ...response, conversation_id: 12 })
    const wrapper = mountChat()
    await wrapper.get('[data-test="restore-id"]').setValue("12")
    await wrapper.get('[data-test="restore"]').trigger("click")
    await flushPromises()

    expect(api.getConversation).toHaveBeenCalledWith(12, 1)
    expect(wrapper.text()).toContain("Historical question")
    expect(wrapper.text()).toContain("Historical answer")

    await submit(wrapper, "Current question")
    expect(api.sendChat).toHaveBeenCalledWith({
      project_id: 1,
      question: "Current question",
      conversation_id: 12,
      limit: 5,
    })
  })
})
