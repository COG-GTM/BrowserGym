import type { ElementBox, ExtraElementProperties } from "../types";

/** Convert BrowserGym `extra_element_properties` into overlay boxes (visible elements with a bbox only). */
export function boxesFromExtraProperties(props: ExtraElementProperties, minVisibility = 0.5): ElementBox[] {
  const boxes: ElementBox[] = [];
  for (const [bid, p] of Object.entries(props)) {
    const b = p.bbox;
    if (!b || b.length !== 4 || (p.visibility ?? 1) < minVisibility) continue;
    boxes.push({
      bid,
      bbox: [b[0]!, b[1]!, b[2]!, b[3]!],
      clickable: Boolean(p.clickable),
      som: Boolean(p.set_of_marks),
    });
  }
  return boxes;
}
