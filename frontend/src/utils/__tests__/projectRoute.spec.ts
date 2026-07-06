import { describe, expect, it } from "vitest"

import { projectIdFromQuery } from "../projectRoute"

describe("projectIdFromQuery", () => {
  it("accepts positive integer strings and rejects malformed values", () => {
    expect(projectIdFromQuery("7")).toBe(7)
    for (const value of [undefined, ["7"], "0", "-2", "2.5", "7x"]) {
      expect(projectIdFromQuery(value)).toBe(1)
    }
  })
})
