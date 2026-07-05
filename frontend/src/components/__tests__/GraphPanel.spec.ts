import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
import { describe, expect, it, vi } from "vitest"

import type { GraphEdge, GraphNode } from "@/types/graph"
import GraphPanel from "../GraphPanel.vue"

const cytoscapeState = vi.hoisted(() => {
  const instances: Array<{
    on: ReturnType<typeof vi.fn>
    destroy: ReturnType<typeof vi.fn>
  }> = []
  const options: unknown[] = []
  const create = vi.fn((value: unknown) => {
    options.push(value)
    const instance = {
      on: vi.fn(),
      destroy: vi.fn(),
    }
    instances.push(instance)
    return instance
  })
  return { create, instances, options }
})

vi.mock("cytoscape", () => ({
  default: cytoscapeState.create,
}))

const nodes: GraphNode[] = [
  {
    entity_id: 1,
    label: "GET /api/alerts/{id}",
    entity_type: "backend_api",
    qualified_name: "GET /api/alerts/{id}",
    file_path: "backend/AlertController.java",
    start_line: 10,
    end_line: 13,
    content: "getAlert()",
    metadata: {},
  },
  {
    entity_id: 2,
    label: "AlertController.getAlert",
    entity_type: "java_method",
    qualified_name: "AlertController.getAlert",
    file_path: "backend/AlertController.java",
    start_line: 10,
    end_line: 13,
    content: "return service.findById(id);",
    metadata: {},
  },
]

const edges: GraphEdge[] = [
  {
    relation_id: 7,
    source_id: 1,
    target_id: 2,
    relation_type: "DEFINES_API",
    confidence: 1,
    metadata: {},
  },
]

describe("GraphPanel", () => {
  it("maps graph data and emits the selected node", async () => {
    const wrapper = mount(GraphPanel, {
      props: { nodes, edges },
    })
    await nextTick()

    const options = cytoscapeState.options.at(-1) as {
      elements: Array<{ data: Record<string, unknown> }>
    }
    expect(options.elements).toHaveLength(3)
    expect(options.elements[2].data.label).toBe("DEFINES_API")

    const instance = cytoscapeState.instances.at(-1)!
    const tapCall = instance.on.mock.calls.find(
      ([event, selector]) => event === "tap" && selector === "node",
    )
    expect(tapCall).toBeTruthy()
    tapCall![2]({
      target: {
        data: (key: string) =>
          key === "entityId" ? nodes[1].entity_id : undefined,
      },
    })

    expect(wrapper.emitted("select-node")?.[0]).toEqual([nodes[1]])
  })

  it("destroys the previous graph on replacement and unmount", async () => {
    const wrapper = mount(GraphPanel, {
      props: { nodes, edges },
    })
    await nextTick()
    const first = cytoscapeState.instances.at(-1)!

    await wrapper.setProps({ nodes: [nodes[0]], edges: [] })
    await nextTick()
    expect(first.destroy).toHaveBeenCalledOnce()
    const second = cytoscapeState.instances.at(-1)!

    wrapper.unmount()
    expect(second.destroy).toHaveBeenCalledOnce()
  })
})
