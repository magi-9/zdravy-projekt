// Zrkadlí `blend_with_white`/`readable_text_color`/`_diet_text_and_background`
// z `backend/api/exporters/gramage_dashboard_export.py` a `gramage_table_spec.py`
// (#536) — aby náhľad vo formulári diéty ukazoval presne to, čo PDF a
// gramážna tabuľka vykreslia, keď admin nezvolí vlastnú farbu textu/pozadia.

const FALLBACK_HEX = "FDE68A";
const COMBO_FALLBACK_BACKGROUND = "F97316";

const normalizeHex = (value: string | undefined | null): string => {
  const clean = (value || "").replace("#", "").toUpperCase();
  return /^[0-9A-F]{6}$/.test(clean) ? clean : FALLBACK_HEX;
};

export const blendWithWhite = (hex: string, opacity = 0.14): string => {
  const rgb = channelsOf(normalizeHex(hex));
  const mixed = rgb.map((channel) => Math.round(255 * (1 - opacity) + channel * opacity));
  return `#${toHex(mixed)}`;
};

export const readableTextColor = (hex: string): string => {
  let rgb = channelsOf(normalizeHex(hex));
  for (let step = 0; step < 10; step += 1) {
    if (luminanceOf(rgb) <= 0.4) break;
    rgb = rgb.map((channel) => Math.round(channel * 0.85));
  }
  return `#${toHex(rgb)}`;
};

function channelsOf(hex6: string): number[] {
  return [0, 2, 4].map((index) => parseInt(hex6.slice(index, index + 2), 16));
}

function luminanceOf([r, g, b]: number[]): number {
  return 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255);
}

function toHex(channels: number[]): string {
  return channels.map((channel) => channel.toString(16).padStart(2, "0").toUpperCase()).join("");
}

export interface DietStyle {
  text: string;
  background: string;
}

/** Predvolená (počítaná) štýlová dvojica pre diétu bez explicitnej vlastnej
 * farby — jedna diéta oboma farbou tej diéty, kombinácia dvoch farbou
 * hlavnej/vedľajšej, tri a viac farbou prvej + pevnou oranžovou. */
export const computedDietStyle = (ownColor: string, baseColors: string[] = []): DietStyle => {
  const colors = baseColors.filter(Boolean);
  let text: string;
  let background: string;
  if (colors.length >= 3) {
    text = colors[0];
    background = `#${COMBO_FALLBACK_BACKGROUND}`;
  } else if (colors.length === 2) {
    text = colors[0];
    background = colors[1];
  } else {
    text = ownColor || `#${FALLBACK_HEX}`;
    background = text;
  }
  return { text: readableTextColor(text), background: blendWithWhite(background) };
};
