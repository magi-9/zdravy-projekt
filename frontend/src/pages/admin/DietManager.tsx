import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, Layers, Plus, Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useToast } from "../../context/ToastContext";
import { logger } from '../../lib/logger';
import { PageHead, Card, Button, IconButton, Field, Input, Textarea, Modal, Empty, ColorSwatchPicker, Checkbox } from "./ui";
import { DietColorSwatch } from "./DietColorSwatch";
import { DietStylePreview } from "./DietStylePreview";
import { computedDietStyle } from "./dietColorMath";
import { dietReorderPayload, moveDietBefore, moveDietBy } from "./dietReorder";

export interface Diet {
  id: number;
  name: string;
  sort_order: number;
  is_active: boolean;
  description: string;
  color?: string;
  text_color?: string;
  background_color?: string;
  base_diets?: number[];
  base_colors?: string[];
}

// Zdieľaný picker + náhľad pre "Farba textu v PDF" / "Farba pozadia v PDF"
// (#536) — prázdna hodnota znamená "automaticky" (dopočíta sa z farby
// diéty/kombinácie na backende, viď `computedDietStyle`), picker preto ako
// predvyplnenú hodnotu ukáže práve tento počítaný predvolený štýl.
const DietStyleFields: React.FC<{
  label: string;
  textColor: string;
  backgroundColor: string;
  onTextColorChange: (value: string) => void;
  onBackgroundColorChange: (value: string) => void;
  computed: { text: string; background: string };
}> = ({ label, textColor, backgroundColor, onTextColorChange, onBackgroundColorChange, computed }) => (
  <>
    <Field label="Farba textu v PDF" as="div" hint="prázdne = automaticky podľa farby diéty">
      <ColorSwatchPicker
        value={textColor || computed.text}
        onChange={onTextColorChange}
        ariaLabel="Farba textu v PDF"
      />
    </Field>
    <Field label="Farba pozadia v PDF" as="div" hint="prázdne = automaticky podľa farby diéty">
      <ColorSwatchPicker
        value={backgroundColor || computed.background}
        onChange={onBackgroundColorChange}
        ariaLabel="Farba pozadia v PDF"
      />
    </Field>
    <Field label="Náhľad" as="div">
      <DietStylePreview
        label={label}
        textColor={textColor || computed.text}
        backgroundColor={backgroundColor || computed.background}
      />
    </Field>
  </>
);

interface DeleteConfirm {
  id: number;
  name: string;
}

interface RenameModal {
  id: number;
  currentName: string;
  newName: string;
  description: string;
  color: string;
  textColor: string;
  backgroundColor: string;
  baseDietIds: number[];
  isComposite: boolean;
}

interface CompositeModal {
  baseDietIds: number[];
  textColor: string;
  backgroundColor: string;
  step: 1 | 2;
}

interface DragState {
  dietId: number;
}

const sameDietIds = (left: number[], right: number[]) =>
  left.length === right.length && left.every((id, index) => id === right[index]);

// `Diet.color` už nemá vlastný picker (#536 — malo by ísť len o farbu textu a
// farbu pozadia, nie o tretí "identity" výber navyše) — ostáva len ako interná
// hodnota pre okrúhly odznak v zozname a pre kombinačnú logiku (base_colors),
// odvodená z toho, čo si admin zvolil pre text/pozadie.
const DEFAULT_DIET_COLOR = "#D83131";
const resolveDietColor = (textColor: string, backgroundColor: string, fallback = DEFAULT_DIET_COLOR) =>
  textColor || backgroundColor || fallback;

// Počet zložiek diéty: nekombinovaná diéta (bez base_diets) je vždy 1-zložková,
// kombinovaná má toľko zložiek, koľko základných diét spája (min. 2).
const componentCount = (diet: Pick<Diet, "base_diets">) =>
  diet.base_diets && diet.base_diets.length > 0 ? diet.base_diets.length : 1;

const COMPONENT_SECTIONS: { label: string; match: (count: number) => boolean }[] = [
  { label: "1-zložkové", match: (count) => count === 1 },
  { label: "2-zložkové", match: (count) => count === 2 },
  { label: "3-zložkové", match: (count) => count === 3 },
  { label: "Viac-zložkové", match: (count) => count >= 4 },
];

// Nová diéta sa vždy zaradí na koniec svojho bloku (podľa počtu zložiek) —
// poradie sa ďalej mení už len drag&drop-om (prípadne šípkami na mobile).
const nextSortOrderForComponentCount = (diets: Diet[], count: number) => {
  const inSameBlock = diets.filter((diet) => componentCount(diet) === count);
  if (inSameBlock.length === 0) return 0;
  return Math.max(...inSameBlock.map((diet) => diet.sort_order || 0)) + 1;
};

const DietManager: React.FC = () => {
  const { apiFetch } = useAuth();
  const { success, error } = useToast();
  const [diets, setDiets] = useState<Diet[]>([]);
  const [newDietName, setNewDietName] = useState("");
  const [newDietDescription, setNewDietDescription] = useState("");
  const [newDietTextColor, setNewDietTextColor] = useState("");
  const [newDietBackgroundColor, setNewDietBackgroundColor] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<DeleteConfirm | null>(null);
  const [renameModal, setRenameModal] = useState<RenameModal | null>(null);
  const [compositeModal, setCompositeModal] = useState<CompositeModal | null>(null);
  const [creatingComposite, setCreatingComposite] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [dragging, setDragging] = useState<DragState | null>(null);
  const saveVersionRef = useRef(0);

  const fetchDiets = useCallback(async () => {
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/`,
      );
      if (res.ok) {
        const data = await res.json();
        setDiets(Array.isArray(data) ? data : data.results || []);
      }
    } catch (e) {
      logger.error(e);
    }
  }, [apiFetch]);

  useEffect(() => {
    fetchDiets();
  }, [fetchDiets]);

  const handleAddDiet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDietName) return;

    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: newDietName.trim(),
            sort_order: nextSortOrderForComponentCount(diets, 1),
            description: newDietDescription.trim(),
            color: resolveDietColor(newDietTextColor, newDietBackgroundColor),
            text_color: newDietTextColor,
            background_color: newDietBackgroundColor,
            base_diets: [],
            is_active: true,
          }),
        },
      );
      if (res.ok) {
        const created = (await res.json()) as Diet;
        setDiets((prev) => {
          if (prev.some((d) => d.id === created.id)) return prev;
          return [...prev, created];
        });
        setNewDietName("");
        setNewDietDescription("");
        setNewDietTextColor("");
        setNewDietBackgroundColor("");
        fetchDiets();
        success("Diéta bola úspešne pridaná");
      } else {
        const data = await res.json().catch(() => ({}));
        error(data?.name?.[0] || "Nepodarilo sa vytvoriť diétu (možno už existuje)");
      }
    } catch (e) {
      logger.error(e);
      error("Chyba pri vytváraní diéty");
    }
  };

  const toggleCompositeDiet = (dietId: number) => {
    setCompositeModal((current) => {
      if (!current) return current;
      const selected = current.baseDietIds.includes(dietId)
        ? current.baseDietIds.filter((id) => id !== dietId)
        : [...current.baseDietIds, dietId];
      return { ...current, baseDietIds: selected };
    });
  };

  const handleAddCompositeDiet = async () => {
    if (!compositeModal || compositeModal.baseDietIds.length < 2) return;
    const selectedDiets = composableDiets.filter((diet) =>
      compositeModal.baseDietIds.includes(diet.id),
    );
    if (selectedDiets.length < 2) return;

    setCreatingComposite(true);
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: selectedDiets.map((diet) => diet.name).join(" – "),
            sort_order: nextSortOrderForComponentCount(diets, selectedDiets.length),
            description: `Kombinácia: ${selectedDiets.map((diet) => diet.name).join(", ")}`,
            color: selectedDiets[0].color || "#D83131",
            text_color: compositeModal.textColor,
            background_color: compositeModal.backgroundColor,
            base_diets: selectedDiets.map((diet) => diet.id),
            is_active: true,
          }),
        },
      );
      if (res.ok) {
        setCompositeModal(null);
        await fetchDiets();
        success("Kombinovaná diéta bola vytvorená");
      } else {
        const data = await res.json().catch(() => ({}));
        error(data?.name?.[0] || "Nepodarilo sa vytvoriť kombinovanú diétu (možno už existuje)");
      }
    } catch (e) {
      logger.error(e);
      error("Chyba pri vytváraní kombinovanej diéty");
    } finally {
      setCreatingComposite(false);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteConfirm) return;
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/${deleteConfirm.id}/`,
        { method: "DELETE" },
      );
      if (res.ok) {
        success(`Diéta "${deleteConfirm.name}" bola odstránená`);
        fetchDiets();
      } else {
        error("Nepodarilo sa odstrániť diétu");
      }
    } catch (e) {
      logger.error(e);
      error("Chyba pri odstraňovaní diéty");
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleRename = async () => {
    if (!renameModal || !renameModal.newName.trim()) return;
    setRenaming(true);
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/${renameModal.id}/`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: renameModal.newName.trim(),
            description: renameModal.description.trim(),
            color: resolveDietColor(renameModal.textColor, renameModal.backgroundColor, renameModal.color),
            text_color: renameModal.textColor,
            background_color: renameModal.backgroundColor,
            base_diets: renameModal.baseDietIds,
          }),
        },
      );
      if (res.ok) {
        success("Diéta bola uložená");
        fetchDiets();
        setRenameModal(null);
      } else {
        const data = await res.json().catch(() => ({}));
        error(data?.name?.[0] || "Nepodarilo sa uložiť diétu (možno názov už existuje)");
      }
    } catch (e) {
      logger.error(e);
      error("Chyba pri ukladaní diéty");
    } finally {
      setRenaming(false);
    }
  };

  const persistDietOrder = async (nextDiets: Diet[]) => {
    const saveVersion = saveVersionRef.current + 1;
    saveVersionRef.current = saveVersion;
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/diets/reorder/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(dietReorderPayload(nextDiets)),
        },
      );
      if (!res.ok) {
        error("Nepodarilo sa uložiť poradie diét.");
        if (saveVersionRef.current === saveVersion) await fetchDiets();
        return;
      }
      const saved = await res.json();
      if (saveVersionRef.current === saveVersion) {
        setDiets(Array.isArray(saved) ? saved : saved.results || []);
      }
    } catch (e) {
      logger.error(e);
      error("Chyba pri ukladaní poradia diét.");
      if (saveVersionRef.current === saveVersion) await fetchDiets();
    }
  };

  const startDrag = (event: React.DragEvent, nextDragging: DragState) => {
    const target = event.target as HTMLElement | null;
    if (target?.closest("button, select, input, textarea, a")) {
      event.preventDefault();
      return;
    }
    setDragging(nextDragging);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-zpa-diet", JSON.stringify(nextDragging));
  };

  const allowDrop = (event: React.DragEvent) => {
    if (!dragging) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const dropDiet = (targetDietId: number) => {
    if (!dragging || dragging.dietId === targetDietId) return;
    const nextDiets = moveDietBefore(diets, dragging.dietId, targetDietId);
    if (nextDiets === diets) return;
    setDiets(nextDiets);
    setDragging(null);
    void persistDietOrder(nextDiets);
  };

  const moveDiet = (dietId: number, delta: number) => {
    const nextDiets = moveDietBy(diets, dietId, delta);
    if (nextDiets === diets) return;
    setDiets(nextDiets);
    void persistDietOrder(nextDiets);
  };

  const composableDiets = diets.filter((diet) => (diet.base_diets || []).length === 0);

  return (
    <>
      <PageHead
        eyebrow="Nastavenia"
        title="Správa diét"
        desc="Pridajte, premenujte alebo upravte popisy systémových diét"
      />

      <div className="zpa-stack">
        <Card pad>
          <form onSubmit={handleAddDiet} className="zpa-formrow">
            <Field label="Názov diéty">
              <Input
                value={newDietName}
                onChange={(e) => setNewDietName(e.target.value)}
                placeholder="Názov novej diéty (napr. Bez lepku)"
              />
            </Field>
            <Field label="Popis" hint="zobrazí sa v gramážnej tabuľke aj PDF priamo pri diéte">
              <Input
                value={newDietDescription}
                onChange={(e) => setNewDietDescription(e.target.value)}
                placeholder="Popis diéty pre prevádzku"
              />
            </Field>
            <DietStyleFields
              label={newDietName}
              textColor={newDietTextColor}
              backgroundColor={newDietBackgroundColor}
              onTextColorChange={setNewDietTextColor}
              onBackgroundColorChange={setNewDietBackgroundColor}
              computed={computedDietStyle(DEFAULT_DIET_COLOR)}
            />
            <Button type="submit" disabled={!newDietName.trim()}>
              <Plus /> Pridať diétu
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={composableDiets.length < 2}
              onClick={() => setCompositeModal({ baseDietIds: [], textColor: "", backgroundColor: "", step: 1 })}
            >
              <Layers /> Vytvoriť kombinovanú
            </Button>
          </form>
        </Card>

        {diets.length === 0 ? (
          <Empty>Zatiaľ nie sú vytvorené žiadne diéty.</Empty>
        ) : (
          COMPONENT_SECTIONS.map((section) => {
            const sectionDiets = diets.filter((diet) => section.match(componentCount(diet)));
            if (sectionDiets.length === 0) return null;
            return (
              <div key={section.label} className="zpa-diet-section">
                <h3 style={{
                  margin: "0 0 10px",
                  fontFamily: "var(--font-display)",
                  fontSize: 13,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--ink-3)",
                }}>
                  {section.label} <span style={{ fontWeight: 400 }}>({sectionDiets.length})</span>
                </h3>
                <div className="zpa-grid-cards">
                  {sectionDiets.map((diet) => {
                    const dietPosition = diets.findIndex((item) => item.id === diet.id);
                    return (
                      <Card
                        key={diet.id}
                        pad
                        className={`zpa-diet-card zpa-draggable-row${dragging?.dietId === diet.id ? " is-dragging" : ""}`}
                        draggable
                        onDragStart={(event) => startDrag(event, { dietId: diet.id })}
                        onDragEnd={() => setDragging(null)}
                        onDragOver={allowDrop}
                        onDrop={(event) => {
                          event.preventDefault();
                          dropDiet(diet.id);
                        }}
                        title="Potiahnutím zmeňte poradie"
                      >
                        <div style={{ minWidth: 0, display: "flex", gap: 12, alignItems: "flex-start" }}>
                          <span className="zpa-row-grip" aria-hidden="true"><GripVertical /></span>
                          <DietColorSwatch color={diet.color} baseColors={diet.base_colors} />
                          <div>
                            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)" }}>{diet.name}</div>
                            {/* Display-only 1-based position in the sorted list — the raw
                                sort_order field is 0-based (and can repeat across diets
                                that were never explicitly reordered), so showing it
                                directly reads as "diéta č. 0". The DB value itself is
                                left untouched; this is purely presentational. */}
                            <p style={{ fontSize: 12, color: "var(--ink-3)", margin: "4px 0 0" }}>Poradie: {dietPosition + 1}</p>
                          {diet.description && (
                            <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "4px 0 0" }}>{diet.description}</p>
                          )}
                          {(diet.base_diets || []).length > 0 && (
                            <p style={{ fontSize: 12, color: "var(--green-700)", margin: "4px 0 0" }}>
                              Kombinácia: {(diet.base_diets || []).map((id) => diets.find((item) => item.id === id)?.name).filter(Boolean).join(" + ")}
                            </p>
                          )}
                          </div>
                        </div>
                        <div className="zpa-rowactions" style={{ flexShrink: 0 }}>
                          <IconButton
                            title="Vyššie"
                            aria-label={`Posunúť diétu ${diet.name} vyššie`}
                            disabled={dietPosition === 0}
                            onClick={() => moveDiet(diet.id, -1)}
                          >
                            <ArrowUp />
                          </IconButton>
                          <IconButton
                            title="Nižšie"
                            aria-label={`Posunúť diétu ${diet.name} nižšie`}
                            disabled={dietPosition === diets.length - 1}
                            onClick={() => moveDiet(diet.id, 1)}
                          >
                            <ArrowDown />
                          </IconButton>
                          <IconButton
                            title="Upraviť"
                            onClick={() =>
                              setRenameModal({
                                id: diet.id,
                                currentName: diet.name,
                                newName: diet.name,
                                description: diet.description || "",
                                color: diet.color || "#D83131",
                                textColor: diet.text_color || "",
                                backgroundColor: diet.background_color || "",
                                baseDietIds: diet.base_diets || [],
                                isComposite: (diet.base_diets || []).length > 0,
                              })
                            }
                          >
                            <Pencil />
                          </IconButton>
                          <IconButton title="Vymazať" onClick={() => setDeleteConfirm({ id: diet.id, name: diet.name })}>
                            <Trash2 />
                          </IconButton>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>

      {compositeModal && (
        <Modal
          title="Vytvoriť kombinovanú diétu"
          onClose={() => setCompositeModal(null)}
          icon={<Layers />}
          iconKind="ok"
          foot={
            <>
              {compositeModal.step === 1 ? (
                <>
                  <Button variant="ghost" onClick={() => setCompositeModal(null)}>Zrušiť</Button>
                  <Button
                    onClick={() => setCompositeModal((current) => current ? { ...current, step: 2 } : current)}
                    disabled={compositeModal.baseDietIds.length < 2}
                  >
                    Pokračovať na farby
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    onClick={() => setCompositeModal((current) => current ? { ...current, step: 1 } : current)}
                  >
                    Späť
                  </Button>
                  <Button onClick={handleAddCompositeDiet} disabled={creatingComposite}>
                    {creatingComposite ? "Vytváram…" : "Vytvoriť kombináciu"}
                  </Button>
                </>
              )}
            </>
          }
        >
          <div className="zpa-step-indicator">Krok {compositeModal.step} z 2</div>
          {compositeModal.step === 1 ? (
            <>
              <p style={{ margin: 0, color: "var(--ink-2)" }}>
                Vyberte aspoň dve existujúce diéty. Názov aj viacfarebné označenie sa vytvoria automaticky.
              </p>
              <div className="zpa-composite-options">
                {composableDiets.map((diet) => (
                  <Checkbox
                    key={diet.id}
                    on={compositeModal.baseDietIds.includes(diet.id)}
                    onChange={() => toggleCompositeDiet(diet.id)}
                  >
                    <DietColorSwatch color={diet.color} size={14} />
                    <span>{diet.name}</span>
                  </Checkbox>
                ))}
              </div>
              {compositeModal.baseDietIds.length > 0 && (
                <div className="zpa-composite-preview">
                  <DietColorSwatch
                    baseColors={compositeModal.baseDietIds.map((id) => diets.find((diet) => diet.id === id)?.color || "")}
                    size={24}
                  />
                  <span>
                    {compositeModal.baseDietIds.map((id) => diets.find((diet) => diet.id === id)?.name).filter(Boolean).join(" – ")}
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="zpa-composite-colour-step">
              <div className="zpa-composite-preview">
                <DietColorSwatch
                  baseColors={compositeModal.baseDietIds.map((id) => diets.find((diet) => diet.id === id)?.color || "")}
                  size={24}
                />
                <span>
                  {compositeModal.baseDietIds.map((id) => diets.find((diet) => diet.id === id)?.name).filter(Boolean).join(" – ")}
                </span>
              </div>
              <DietStyleFields
                label={compositeModal.baseDietIds
                  .map((id) => diets.find((diet) => diet.id === id)?.name)
                  .filter(Boolean)
                  .join(" – ")}
                textColor={compositeModal.textColor}
                backgroundColor={compositeModal.backgroundColor}
                onTextColorChange={(value) =>
                  setCompositeModal((current) => (current ? { ...current, textColor: value } : current))
                }
                onBackgroundColorChange={(value) =>
                  setCompositeModal((current) => (current ? { ...current, backgroundColor: value } : current))
                }
                computed={computedDietStyle(
                  "",
                  compositeModal.baseDietIds
                    .map((id) => diets.find((diet) => diet.id === id)?.color || "")
                    .filter(Boolean),
                )}
              />
            </div>
          )}
        </Modal>
      )}

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <Modal
          title="Odstrániť diétu"
          onClose={() => setDeleteConfirm(null)}
          icon={<Trash2 />}
          iconKind="danger"
          foot={
            <>
              <Button variant="ghost" onClick={() => setDeleteConfirm(null)}>Zrušiť</Button>
              <Button variant="danger" onClick={handleDeleteConfirmed}>Áno, vymazať</Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--ink-2)" }}>
            Naozaj chcete odstrániť diétu{" "}
            <strong style={{ color: "var(--green-900)" }}>„{deleteConfirm.name}"</strong>? Táto akcia sa nedá vrátiť.
          </p>
        </Modal>
      )}

      {/* Rename modal */}
      {renameModal && (
        <Modal
          title="Upraviť diétu"
          onClose={() => setRenameModal(null)}
          foot={
            <>
              <Button variant="ghost" onClick={() => setRenameModal(null)}>Zrušiť</Button>
              <Button
                onClick={handleRename}
                disabled={
                  renaming ||
                  !renameModal.newName.trim() ||
                  (renameModal.isComposite && renameModal.baseDietIds.length < 2) ||
                  (renameModal.newName.trim() === renameModal.currentName &&
                    renameModal.description.trim() ===
                      (diets.find((diet) => diet.id === renameModal.id)?.description || "").trim() &&
                    renameModal.textColor === (diets.find((diet) => diet.id === renameModal.id)?.text_color || "") &&
                    renameModal.backgroundColor ===
                      (diets.find((diet) => diet.id === renameModal.id)?.background_color || ""))
                    && sameDietIds(
                      renameModal.baseDietIds,
                      diets.find((diet) => diet.id === renameModal.id)?.base_diets || [],
                    )
                }
              >
                {renaming ? "Ukladám…" : "Uložiť"}
              </Button>
            </>
          }
        >
          <Field label="Nový názov" hint={`aktuálne: ${renameModal.currentName}`}>
            <Input
              value={renameModal.newName}
              onChange={(e) => setRenameModal((prev) => (prev ? { ...prev, newName: e.target.value } : prev))}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                if (renaming || !renameModal.newName.trim()) return;
                if (renameModal.newName.trim() === renameModal.currentName) return;
                handleRename();
              }}
              placeholder="Nový názov diéty"
              autoFocus
            />
          </Field>
          <Field label="Popis" hint="zobrazí sa v gramážnej tabuľke aj PDF priamo pri diéte">
            <Textarea
              value={renameModal.description}
              onChange={(e) => setRenameModal((prev) => (prev ? { ...prev, description: e.target.value } : prev))}
              placeholder="Popis diéty pre prevádzku"
              rows={4}
            />
          </Field>
          {renameModal.isComposite && (
            <Field label="Zloženie kombinácie" as="div">
              <div className="zpa-composite-options">
                {composableDiets.filter((diet) => diet.id !== renameModal.id).map((diet) => (
                  <Checkbox
                    key={diet.id}
                    on={renameModal.baseDietIds.includes(diet.id)}
                    onChange={(selected) => setRenameModal((current) => current ? {
                      ...current,
                      baseDietIds: selected
                        ? [...current.baseDietIds, diet.id]
                        : current.baseDietIds.filter((id) => id !== diet.id),
                    } : current)}
                  >
                    <DietColorSwatch color={diet.color} size={14} />
                    <span>{diet.name}</span>
                  </Checkbox>
                ))}
              </div>
            </Field>
          )}
          <DietStyleFields
            label={renameModal.newName || renameModal.currentName}
            textColor={renameModal.textColor}
            backgroundColor={renameModal.backgroundColor}
            onTextColorChange={(value) =>
              setRenameModal((prev) => (prev ? { ...prev, textColor: value } : prev))
            }
            onBackgroundColorChange={(value) =>
              setRenameModal((prev) => (prev ? { ...prev, backgroundColor: value } : prev))
            }
            computed={
              renameModal.isComposite
                ? computedDietStyle(
                    "",
                    renameModal.baseDietIds.map((id) => diets.find((diet) => diet.id === id)?.color || "").filter(Boolean),
                  )
                : computedDietStyle(renameModal.color)
            }
          />
        </Modal>
      )}
    </>
  );
};

export default DietManager;
