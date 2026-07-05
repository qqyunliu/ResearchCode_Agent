import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ProjectView from "../ProjectView.vue"

const api = vi.hoisted(() => ({
  createProject: vi.fn(),
  getProjectStats: vi.fn(),
  scanProject: vi.fn(),
}))
vi.mock("@/api/projects", () => api)

const stats = {
  project_id: 7,
  total_files: 12,
  total_lines: 480,
  languages: { java: 8, vue: 4 },
  entity_types: { java_method: 20 },
  relation_types: { CALLS_METHOD: 9 },
  backend_api_count: 3,
  frontend_api_call_count: 2,
  skipped_files: 1,
  parse_errors: 0,
  last_scan_at: "2026-07-05T12:00:00Z",
}

describe("ProjectView", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("requires a name and root path before registration", async () => {
    const wrapper = mount(ProjectView)
    expect(wrapper.get('[data-test="register"]').attributes("disabled"))
      .toBeDefined()

    await wrapper.get('[data-test="project-name"]').setValue("Demo")
    await wrapper.get('[data-test="root-path"]').setValue("F:/demo")

    expect(wrapper.get('[data-test="register"]').attributes("disabled"))
      .toBeUndefined()
  })

  it("registers a project and enables scanning", async () => {
    api.createProject.mockResolvedValue({
      id: 7,
      name: "Demo",
      root_path: "F:/demo",
      status: "created",
    })
    const wrapper = mount(ProjectView)
    await wrapper.get('[data-test="project-name"]').setValue("Demo")
    await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
    await wrapper.get('[data-test="register-form"]').trigger("submit")
    await flushPromises()

    expect(api.createProject).toHaveBeenCalledWith({
      name: "Demo",
      root_path: "F:/demo",
    })
    expect(wrapper.get('[data-test="project-id"]').text()).toContain("7")
    expect(wrapper.get('[data-test="scan"]').attributes("disabled"))
      .toBeUndefined()
  })

  it("scans the project and refreshes its statistics", async () => {
    api.createProject.mockResolvedValue({
      id: 7,
      name: "Demo",
      root_path: "F:/demo",
      status: "created",
    })
    api.scanProject.mockResolvedValue({
      project_id: 7,
      status: "ready",
      files_indexed: 12,
      entities_indexed: 20,
      relations_indexed: 9,
      files_skipped: 1,
      parse_errors: 0,
    })
    api.getProjectStats.mockResolvedValue(stats)
    const wrapper = mount(ProjectView)
    await wrapper.get('[data-test="project-name"]').setValue("Demo")
    await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
    await wrapper.get('[data-test="register-form"]').trigger("submit")
    await flushPromises()
    await wrapper.get('[data-test="scan"]').trigger("click")
    await flushPromises()

    expect(api.scanProject).toHaveBeenCalledWith(7)
    expect(api.getProjectStats).toHaveBeenCalledWith(7)
    expect(wrapper.get('[data-test="stats"]').text()).toContain("12")
    expect(wrapper.get('[data-test="stats"]').text()).toContain("480")
    expect(wrapper.get('[data-test="stats"]').text()).toContain("3")
  })

  it("shows an API error and restores the action", async () => {
    api.createProject.mockRejectedValue(new Error("offline"))
    const wrapper = mount(ProjectView)
    await wrapper.get('[data-test="project-name"]').setValue("Demo")
    await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
    await wrapper.get('[data-test="register-form"]').trigger("submit")
    await flushPromises()

    expect(wrapper.get('[data-test="error"]').text()).toContain(
      "Unable to register",
    )
    expect(wrapper.get('[data-test="register"]').attributes("disabled"))
      .toBeUndefined()
  })
})
