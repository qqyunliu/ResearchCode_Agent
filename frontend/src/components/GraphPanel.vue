<script setup lang="ts">
import cytoscape, { type Core, type EventObject } from "cytoscape"
import { nextTick, onBeforeUnmount, ref, watch } from "vue"

import type { GraphEdge, GraphNode } from "@/types/graph"

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
}>()

const emit = defineEmits<{
  "select-node": [node: GraphNode]
}>()

const container = ref<HTMLElement | null>(null)
let graph: Core | null = null

function destroyGraph() {
  graph?.destroy()
  graph = null
}

function buildGraph() {
  destroyGraph()
  if (!container.value || props.nodes.length === 0) {
    return
  }

  const nodeById = new Map(
    props.nodes.map((node) => [node.entity_id, node]),
  )
  graph = cytoscape({
    container: container.value,
    elements: [
      ...props.nodes.map((node) => ({
        data: {
          id: String(node.entity_id),
          entityId: node.entity_id,
          label: node.label,
          entityType: node.entity_type,
        },
      })),
      ...props.edges.map((edge) => ({
        data: {
          id: `edge-${edge.relation_id}`,
          source: String(edge.source_id),
          target: String(edge.target_id),
          label: edge.relation_type,
          confidence: edge.confidence,
        },
      })),
    ],
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "background-color": "#64748b",
          color: "#0f172a",
          "font-size": "11px",
          "text-wrap": "wrap",
          "text-max-width": "130px",
          "text-valign": "bottom",
          "text-margin-y": 8,
          width: 38,
          height: 38,
        },
      },
      {
        selector: 'node[entityType = "frontend_api_call"]',
        style: { "background-color": "#8b5cf6" },
      },
      {
        selector: 'node[entityType = "backend_api"]',
        style: { "background-color": "#0ea5e9" },
      },
      {
        selector: 'node[entityType = "java_method"]',
        style: { "background-color": "#10b981" },
      },
      {
        selector: 'node[entityType = "java_class"]',
        style: { "background-color": "#f59e0b" },
      },
      {
        selector: "edge",
        style: {
          label: "data(label)",
          width: 2,
          "line-color": "#94a3b8",
          "target-arrow-color": "#94a3b8",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "font-size": "9px",
          color: "#475569",
          "text-background-color": "#f8fafc",
          "text-background-opacity": 0.9,
          "text-background-padding": "3px",
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#0f172a",
          "border-width": 3,
        },
      },
    ],
    layout: {
      name: "breadthfirst",
      directed: true,
      spacingFactor: 1.4,
      padding: 32,
    },
  })

  graph.on("tap", "node", (event: EventObject) => {
    const entityId = Number(event.target.data("entityId"))
    const selected = nodeById.get(entityId)
    if (selected) {
      emit("select-node", selected)
    }
  })
}

watch(
  [() => props.nodes, () => props.edges],
  async () => {
    await nextTick()
    buildGraph()
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(destroyGraph)
</script>

<template>
  <div
    ref="container"
    class="graph-canvas"
    aria-label="代码关系图"
  />
</template>

<style scoped>
.graph-canvas {
  width: 100%;
  min-height: 560px;
  border-radius: 20px;
  background:
    linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    #f8fafc;
  background-size: 24px 24px;
}
</style>
