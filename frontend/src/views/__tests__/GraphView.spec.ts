import { flushPromises, mount } from "@vue/test-utils"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { GraphResponse } from "@/types/graph"
import GraphView from "../GraphView.vue"

const searchChain = vi.hoisted(() => vi.fn())
vi.mock("@/api/graph", () => ({ searchChain }))

const graphResponse: GraphResponse = {
  nodes: [
    {
      entity_id: 5,
      label: "AlertController.getAlert",
      entity_type: "java_method",
      qualified_name: "AlertController.getAlert",
      file_path: "backend/src/AlertController.java",
      start_line: 10,
      end_line: 13,
      content: "return alertService.findById(id);",
      metadata: {},
    },
  ],
  edges: [],
  references: [],
}

const GraphPanelStub = defineComponent({
  props: ["nodes", "edges"],
  emits: ["select-node"],
  template: '<button data-test="select" @click="$emit(\'select-node\', nodes[0])">graph</button>',
})

function mountView() {
  return mount(GraphView, {
    global: {
      stubs: { GraphPanel: GraphPanelStub },
    },
  })
}

describe("GraphView", () => {
  beforeEach(() => {
    searchChain.mockReset()
  })

  it("renders Chinese graph-explorer copy", () => {
    const wrapper = mountView()

    expect(wrapper.get("main").classes()).toContain("page")
    expect(wrapper.get("main").classes()).not.toContain("page-shell")
    expect(wrapper.text()).toContain("从请求追踪到代码实现")
    expect(wrapper.text()).toContain("代码或功能")
    expect(wrapper.get('[data-test="search"]').text()).toContain("追踪调用链")
  })

  it("disables search for a blank query", async () => {
    const wrapper = mountView()
    const button = wrapper.get('[data-test="search"]')

    expect(button.attributes("disabled")).toBeDefined()
    await wrapper.get('[data-test="query"]').setValue("alert API")
    expect(button.attributes("disabled")).toBeUndefined()
  })

  it("loads graph data and shows selected node details", async () => {
    searchChain.mockResolvedValue(graphResponse)
    const wrapper = mountView()
    await wrapper.get('[data-test="query"]').setValue("alert API")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(searchChain).toHaveBeenCalledWith({
      project_id: 1,
      query: "alert API",
      limit: 5,
      max_depth: 2,
    })
    expect(wrapper.findComponent(GraphPanelStub).props("nodes")).toEqual(
      graphResponse.nodes,
    )
    await wrapper.get('[data-test="select"]').trigger("click")
    expect(wrapper.text()).toContain("backend/src/AlertController.java")
    expect(wrapper.text()).toContain("10–13")
    expect(wrapper.text()).toContain("alertService.findById")
  })

  it("shows empty and error states", async () => {
    searchChain.mockResolvedValueOnce({
      nodes: [],
      edges: [],
      references: [],
    })
    const wrapper = mountView()
    await wrapper.get('[data-test="query"]').setValue("missing")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)

    searchChain.mockRejectedValueOnce(new Error("network down"))
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain(
      "无法加载关系图谱",
    )
  })
})
