import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ProjectDeleteDialog from "../ProjectDeleteDialog.vue"

describe("ProjectDeleteDialog", () => {
  it("requires the exact project name", async () => {
    const wrapper = mount(ProjectDeleteDialog, {
      props: { project: { id: 1, name: "Demo" }, deleting: false },
    })
    const button = wrapper.get('[data-test="confirm-delete"]')
    expect(button.attributes("disabled")).toBeDefined()
    await wrapper.get('[data-test="delete-name"]').setValue("demo")
    expect(button.attributes("disabled")).toBeDefined()
    await wrapper.get('[data-test="delete-name"]').setValue("Demo")
    expect(button.attributes("disabled")).toBeUndefined()
    await button.trigger("click")
    expect(wrapper.emitted("confirm")).toHaveLength(1)
  })

  it("shows a deletion failure inside the dialog", () => {
    const wrapper = mount(ProjectDeleteDialog, {
      props: {
        project: { id: 1, name: "Demo" },
        deleting: false,
        error: "删除失败，项目数据已保留。",
      },
    })
    expect(wrapper.get('[data-test="delete-error"]').text()).toContain("数据已保留")
  })
})
