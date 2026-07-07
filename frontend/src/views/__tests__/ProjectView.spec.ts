import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ProjectView from "../ProjectView.vue"
import projectViewSource from "../ProjectView.vue?raw"

const api = vi.hoisted(() => ({
  buildVectorIndex: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
  getProjectStats: vi.fn(),
  getVectorIndexStatus: vi.fn(),
  listProjects: vi.fn(),
  reorderProjects: vi.fn(),
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

function configureSuccessfulScan() {
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
}

async function registerAndScan(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-test="project-name"]').setValue("Demo")
  await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
  await wrapper.get('[data-test="register-form"]').trigger("submit")
  await flushPromises()
  await wrapper.get('[data-test="scan"]').trigger("click")
  await flushPromises()
}

describe("ProjectView", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listProjects.mockResolvedValue([])
    api.getVectorIndexStatus.mockResolvedValue({ project_id: 1, ready: false })
  })

  it("loads history and selects an existing project", async () => {
    api.listProjects.mockResolvedValue([{
      id: 9, name: "Existing", root_path: "F:/existing", status: "ready",
      created_at: "2026-01-01", last_scan_at: "2026-01-02",
      sort_order: 0, path_accessible: true,
    }])
    api.getProjectStats.mockResolvedValue({ ...stats, project_id: 9 })
    const wrapper = mount(ProjectView)
    await flushPromises()
    expect(api.listProjects).toHaveBeenCalled()
    expect(wrapper.text()).toContain("Existing")
    expect(api.getProjectStats).toHaveBeenCalledWith(9)
  })

  it("requires confirmation before rebuilding an existing vector index", async () => {
    api.listProjects.mockResolvedValue([{
      id: 9, name: "Indexed", root_path: "F:/indexed", status: "ready",
      created_at: "2026-01-01", last_scan_at: "2026-01-02",
      sort_order: 0, path_accessible: true,
    }])
    api.getProjectStats.mockResolvedValue({ ...stats, project_id: 9 })
    api.getVectorIndexStatus.mockResolvedValue({ project_id: 9, ready: true })
    api.buildVectorIndex.mockResolvedValue({
      project_id: 9, collection_name: "project_9_code_chunks",
      chunks_indexed: 12,
    })
    const wrapper = mount(ProjectView)
    await flushPromises()
    expect(wrapper.get('[data-test="build-index"]').text()).toContain("重新构建")
    await wrapper.get('[data-test="build-index"]').trigger("click")
    expect(wrapper.get('[data-test="rebuild-confirm"]').text()).toContain("Embedding")
    expect(api.buildVectorIndex).not.toHaveBeenCalled()
    await wrapper.get('[data-test="confirm-rebuild"]').trigger("click")
    await flushPromises()
    expect(api.buildVectorIndex).toHaveBeenCalledWith(9)
  })

  it("renders Chinese project-management copy", () => {
    const wrapper = mount(ProjectView)

    expect(wrapper.text()).toContain("注册并分析代码库")
    expect(wrapper.text()).toContain("项目名称")
    expect(wrapper.text()).toContain("绝对根路径")
    expect(wrapper.get('[data-test="register"]').text()).toContain("注册项目")
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

  it("matches the search page action button height for registration", () => {
    expect(projectViewSource).toContain(
      "form button{align-self:end;padding:13px 20px",
    )
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
      "无法注册项目",
    )
    expect(wrapper.get('[data-test="register"]').attributes("disabled"))
      .toBeUndefined()
  })

  it("enables indexing after scan and displays the index summary", async () => {
    configureSuccessfulScan()
    api.buildVectorIndex.mockResolvedValue({
      project_id: 7,
      collection_name: "project_7_code_chunks",
      chunks_indexed: 31,
    })
    const wrapper = mount(ProjectView)
    await wrapper.get('[data-test="project-name"]').setValue("Demo")
    await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
    await wrapper.get('[data-test="register-form"]').trigger("submit")
    await flushPromises()
    expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
      .toBeDefined()

    await wrapper.get('[data-test="scan"]').trigger("click")
    await flushPromises()
    expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
      .toBeUndefined()
    await wrapper.get('[data-test="build-index"]').trigger("click")
    await flushPromises()

    expect(api.buildVectorIndex).toHaveBeenCalledWith(7)
    expect(wrapper.get('[data-test="index-result"]').text()).toContain("31")
    expect(wrapper.get('[data-test="index-result"]').text()).toContain(
      "project_7_code_chunks",
    )
  })

  it("shows indexing progress and disables conflicting actions", async () => {
    configureSuccessfulScan()
    let finish!: (value: {
      project_id: number
      collection_name: string
      chunks_indexed: number
    }) => void
    api.buildVectorIndex.mockReturnValue(new Promise((resolve) => {
      finish = resolve
    }))
    const wrapper = mount(ProjectView)
    await registerAndScan(wrapper)
    await wrapper.get('[data-test="build-index"]').trigger("click")

    expect(wrapper.get('[data-test="build-index"]').text()).toContain(
      "正在构建索引",
    )
    expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
      .toBeDefined()
    expect(wrapper.get('[data-test="scan"]').attributes("disabled"))
      .toBeDefined()

    finish({
      project_id: 7,
      collection_name: "project_7_code_chunks",
      chunks_indexed: 31,
    })
    await flushPromises()
  })

  it("keeps scan results and permits retry after index failure", async () => {
    configureSuccessfulScan()
    api.buildVectorIndex
      .mockRejectedValueOnce(new Error("embedding unavailable"))
      .mockResolvedValueOnce({
        project_id: 7,
        collection_name: "project_7_code_chunks",
        chunks_indexed: 31,
      })
    const wrapper = mount(ProjectView)
    await registerAndScan(wrapper)
    await wrapper.get('[data-test="build-index"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-test="error"]').text()).toContain(
      "无法构建向量索引",
    )
    expect(wrapper.find('[data-test="stats"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
      .toBeUndefined()

    await wrapper.get('[data-test="build-index"]').trigger("click")
    await flushPromises()
    expect(api.buildVectorIndex).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="error"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="index-result"]').text()).toContain("31")
  })
})
