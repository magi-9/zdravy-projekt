import { describe, expect, it } from "vitest";
import { blendWithWhite, computedDietStyle, readableTextColor } from "./dietColorMath";

// Zamyká paritu s `readable_text_color`/`blend_with_white` v
// `backend/api/exporters/gramage_dashboard_export.py` (#536) — hodnoty tu sú
// prevzaté priamo z `backend/api/tests/test_gramage_table_spec.py`.

describe("readableTextColor", () => {
  it("darkens a pale colour until it is legible", () => {
    expect(readableTextColor("#F59E0B")).toBe("#966107");
  });
});

describe("blendWithWhite", () => {
  it("mixes a diet colour with white at 14% opacity", () => {
    expect(blendWithWhite("#F59E0B")).toBe(blendWithWhite("F59E0B"));
  });
});

describe("computedDietStyle", () => {
  it("uses the same colour for text and background for a single diet", () => {
    const style = computedDietStyle("#F59E0B");
    expect(style.text).toBe(readableTextColor("#F59E0B"));
    expect(style.background).toBe(blendWithWhite("#F59E0B"));
  });

  it("uses main/secondary for a combination of two", () => {
    const style = computedDietStyle("#000000", ["#F59E0B", "#EF4444"]);
    expect(style.text).toBe(readableTextColor("#F59E0B"));
    expect(style.background).toBe(blendWithWhite("#EF4444"));
  });

  it("uses a fixed orange background for a combination of three or more", () => {
    const style = computedDietStyle("#000000", ["#F59E0B", "#EF4444", "#16A34A"]);
    expect(style.text).toBe(readableTextColor("#F59E0B"));
    expect(style.background).toBe(blendWithWhite("#F97316"));
  });
});
