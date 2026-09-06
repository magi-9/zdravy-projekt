import React from "react";

interface DietStylePreviewProps {
  label: string;
  textColor?: string;
  backgroundColor?: string;
}

// Náhľad presne toho, čo diéta dostane v gramážnej tabuľke aj v PDF: meno
// diéty ako text danej farby na podfarbenom pozadí. Keď farba nie je (ešte)
// vybraná, ukazuje sa neutrálny predvolený pár, nie prázdne miesto — admin
// tak hneď vidí, že "žiadny výber" tiež vyzerá ako platný stav (#536).
export const DietStylePreview: React.FC<DietStylePreviewProps> = ({
  label,
  textColor,
  backgroundColor,
}) => (
  <div
    data-testid="diet-style-preview"
    style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "8px 16px",
      borderRadius: 8,
      fontFamily: "var(--font-display)",
      fontWeight: 600,
      fontSize: 13,
      color: textColor || "var(--green-900)",
      background: backgroundColor || "var(--cream-soft, #F5F1CD)",
      boxShadow: "inset 0 0 0 1px rgba(39, 52, 34, 0.18)",
    }}
  >
    {label.trim() || "Ukážka textu"}
  </div>
);
