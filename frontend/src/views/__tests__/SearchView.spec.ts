import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import SearchView from "../SearchView.vue"
import searchViewSource from "../SearchView.vue?raw"

const hybridSearch = vi.hoisted(() => vi.fn())
vi.mock("@/api/search", () => ({ hybridSearch }))

describe("SearchView", () => {
  beforeEach(() => {
    hybridSearch.mockReset()
    localStorage.clear()
    window.history.pushState({}, "", "/")
  })

  it("prefills project ID from the URL query", () => {
    window.history.pushState({}, "", "/search?project_id=17")
    const wrapper = mount(SearchView)
    expect((wrapper.get('[data-test="project-id"]').element as HTMLInputElement).value).toBe("17")
    window.history.pushState({}, "", "/")
  })

  it("renders Chinese search copy", () => {
    const wrapper = mount(SearchView)

    expect(wrapper.text()).toContain("按语义和关键词查找代码")
    expect(wrapper.text()).toContain("项目 ID")
    expect(wrapper.get('[data-test="search"]').text()).toContain("搜索代码")
  })

  it("keeps form inputs inside their grid columns", () => {
    expect(searchViewSource).toMatch(
      /input\s*\{[^}]*box-sizing:\s*border-box;[^}]*min-width:\s*0;[^}]*width:\s*100%;[^}]*\}/s,
    )
  })

  it("requires a positive project ID and nonblank query", async () => {
    const wrapper = mount(SearchView)
    expect(wrapper.get('[data-test="search"]').attributes("disabled"))
      .toBeDefined()

    await wrapper.get('[data-test="query"]').setValue("alert API")
    expect(wrapper.get('[data-test="search"]').attributes("disabled"))
      .toBeUndefined()
    await wrapper.get('[data-test="project-id"]').setValue("0")
    expect(wrapper.get('[data-test="search"]').attributes("disabled"))
      .toBeDefined()
  })

  it("submits hybrid search and renders result details", async () => {
    hybridSearch.mockResolvedValue([
      {
        entity_id: 5,
        entity_type: "java_method",
        name: "getAlert",
        qualified_name: "AlertController.getAlert",
        file_path: "backend/src/AlertController.java",
        start_line: 10,
        end_line: 13,
        content: "return service.find();",
        metadata: {},
        score: 0.92,
        source: "hybrid",
      },
    ])
    const wrapper = mount(SearchView)
    await wrapper.get('[data-test="query"]').setValue(" alert API ")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(hybridSearch).toHaveBeenCalledWith({
      project_id: 1,
      query: "alert API",
      limit: 10,
    })
    const result = wrapper.get('[data-test="result"]')
    expect(result.text()).toContain("AlertController.getAlert")
    expect(result.text()).toContain("backend/src/AlertController.java")
    expect(result.text()).toContain("10–13")
    expect(result.text()).toContain("0.920")
    expect(result.text()).toContain("hybrid")
  })

  it("records successful searches and refreshes results from history", async () => {
    hybridSearch
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          entity_id: 9,
          entity_type: "java_method",
          name: "findAlert",
          qualified_name: "AlertService.findAlert",
          file_path: "backend/src/AlertService.java",
          start_line: 20,
          end_line: 24,
          content: "return repository.findAlert();",
          metadata: {},
          score: 0.88,
          source: "hybrid",
        },
      ])
    const wrapper = mount(SearchView)
    await wrapper.get('[data-test="project-id"]').setValue("3")
    await wrapper.get('[data-test="query"]').setValue(" alert API ")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    const item = wrapper.get('[data-test="history-item"]')
    expect(item.text()).toContain("alert API")
    expect(item.text()).toContain("项目 ID 3")

    await wrapper.get('[data-test="query"]').setValue("other")
    await item.trigger("click")

    expect((wrapper.get('[data-test="project-id"]').element as HTMLInputElement).value).toBe("3")
    expect((wrapper.get('[data-test="query"]').element as HTMLInputElement).value).toBe("alert API")
    await flushPromises()

    expect(hybridSearch).toHaveBeenCalledTimes(2)
    expect(hybridSearch).toHaveBeenLastCalledWith({
      project_id: 3,
      query: "alert API",
      limit: 10,
    })
    expect(wrapper.get('[data-test="result"]').text()).toContain("AlertService.findAlert")
  })

  it("deletes one search history item and clears all history", async () => {
    hybridSearch.mockResolvedValue([])
    const wrapper = mount(SearchView)
    await wrapper.get('[data-test="query"]').setValue("alert API")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    await wrapper.get('[data-test="query"]').setValue("login controller")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(wrapper.findAll('[data-test="history-item"]')).toHaveLength(2)

    await wrapper.get('[data-test="delete-history-item"]').trigger("click")
    expect(wrapper.findAll('[data-test="history-item"]')).toHaveLength(1)

    await wrapper.get('[data-test="clear-history"]').trigger("click")
    expect(wrapper.find('[data-test="search-history"]').exists()).toBe(false)
  })

  it("shows empty and error states", async () => {
    hybridSearch.mockResolvedValueOnce([])
    const wrapper = mount(SearchView)
    await wrapper.get('[data-test="query"]').setValue("missing")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)

    hybridSearch.mockRejectedValueOnce(new Error("offline"))
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain(
      "无法搜索",
    )
  })
})
