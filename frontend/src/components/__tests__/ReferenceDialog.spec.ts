import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ReferenceDialog from "../ReferenceDialog.vue"

const reference = {
  citation: 1,
  entity_id: 5,
  file_path: "backend/src/AlertController.java",
  start_line: 10,
  end_line: 13,
  entity_type: "java_method",
  qualified_name: "AlertController.getAlert",
}

describe("ReferenceDialog", () => {
  it("shows reference metadata and indexed code", () => {
    const wrapper = mount(ReferenceDialog, {
      props: {
        reference,
        content: "return alertService.find();",
        loading: false,
        error: "",
      },
    })

    expect(wrapper.text()).toContain("AlertController.getAlert")
    expect(wrapper.text()).toContain("backend/src/AlertController.java")
    expect(wrapper.text()).toContain("10–13")
    expect(wrapper.text()).toContain("return alertService.find()")
    expect(wrapper.text()).toContain("行号")
    expect(wrapper.get('[data-test="close-reference"]').attributes("aria-label"))
      .toBe("关闭引用详情")
  })

  it("emits close and exposes loading and error states", async () => {
    const wrapper = mount(ReferenceDialog, {
      props: {
        reference,
        content: "",
        loading: true,
        error: "",
      },
    })
    expect(wrapper.find('[data-test="reference-loading"]').exists()).toBe(true)

    await wrapper.setProps({ loading: false, error: "无法加载引用代码。" })
    expect(wrapper.get('[data-test="reference-error"]').text()).toContain(
      "无法加载引用代码",
    )
    await wrapper.get('[data-test="close-reference"]').trigger("click")
    expect(wrapper.emitted("close")).toHaveLength(1)
  })
})
