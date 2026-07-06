import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { mount } from "@vue/test-utils"
import { createMemoryHistory, createRouter } from "vue-router"
import { describe, expect, it } from "vitest"

import App from "@/App.vue"
import { routes } from "@/router"

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes,
  })
}

describe("application router", () => {
  it("declares Chinese document metadata", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8")

    expect(html).toContain('<html lang="zh-CN">')
    expect(html).toContain("<title>ResearchCode-Agent 代码理解助手</title>")
    expect(html).toContain("科研代码库理解与关系分析")
  })

  it("redirects the root route to projects", async () => {
    const router = testRouter()
    await router.push("/")
    await router.isReady()

    expect(router.currentRoute.value.path).toBe("/projects")
  })

  it("defines project, search, and graph routes", () => {
    expect(routes.map((route) => route.path)).toEqual([
      "/",
      "/projects",
      "/search",
      "/graph",
      "/chat",
    ])
  })

  it("renders navigation links around the current page", async () => {
    const router = testRouter()
    await router.push("/projects")
    await router.isReady()
    const wrapper = mount(App, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("项目")
    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("代码搜索")
    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("关系图谱")
    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("Agent 对话")
  })
})
