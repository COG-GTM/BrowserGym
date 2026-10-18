import { expect, it } from "vitest";
import { boxesFromExtraProperties } from "./boxes";

it("converts extra_element_properties to boxes, skipping invisible / bbox-less elements", () => {
  expect(
    boxesFromExtraProperties({
      a1: { visibility: 1, bbox: [1, 2, 3, 4], clickable: true, set_of_marks: 1 },
      a2: { visibility: 0.1, bbox: [0, 0, 1, 1] },
      a3: { visibility: 1, bbox: null },
    }),
  ).toEqual([{ bid: "a1", bbox: [1, 2, 3, 4], clickable: true, som: true }]);
});
