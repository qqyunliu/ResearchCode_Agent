import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ProjectHistoryList from "../ProjectHistoryList.vue"
import projectHistorySource from "../ProjectHistoryList.vue?raw"
import type { Project } from "@/types/project"

const projects: Project[] = [
  { id: 2, name: "Beta", root_path: "F:/beta", status: "ready", created_at: "2026-02-01", last_scan_at: "2026-02-02", sort_order: 0, path_accessible: true },
  { id: 1, name: "Alpha", root_path: "F:/alpha", status: "created", created_at: "2026-01-01", last_scan_at: null, sort_order: 1, path_accessible: false },
]

describe("ProjectHistoryList", () => {
  it("separates the heading from the search field", () => {
    expect(projectHistorySource).toMatch(
      /\.history-head[^}]*margin-bottom:\s*14px/,
    )
  })

  it("filters projects and emits selection", async () => {
    const wrapper = mount(ProjectHistoryList, { props: { projects, selectedProjectId: 2, loading: false } })
    await wrapper.get('[data-test="history-search"]').setValue("alpha")
    expect(wrapper.findAll('[data-test="history-item"]')).toHaveLength(1)
    await wrapper.get('[data-test="history-item"]').trigger("click")
    expect(wrapper.emitted("select")?.[0]).toEqual([1])
    expect(wrapper.text()).toContain("不可访问")
  })
})
