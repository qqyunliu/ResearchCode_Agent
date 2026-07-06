import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ProjectReorderList from "../ProjectReorderList.vue"

const projects = [
  { id: 1, name: "One" },
  { id: 2, name: "Two" },
]

describe("ProjectReorderList", () => {
  it("reorders a draft and emits every ID on save", async () => {
    const wrapper = mount(ProjectReorderList, { props: { projects, saving: false } })
    const items = wrapper.findAll('[data-test="reorder-item"]')
    await items[0].trigger("dragstart")
    await items[1].trigger("drop")
    await wrapper.get('[data-test="save-order"]').trigger("click")
    expect(wrapper.emitted("save")?.[0]).toEqual([[2, 1]])
  })
})
