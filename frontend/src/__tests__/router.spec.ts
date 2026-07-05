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

    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("Projects")
    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("Search")
    expect(wrapper.get('[data-test="app-nav"]').text()).toContain("Graph")
  })
})
