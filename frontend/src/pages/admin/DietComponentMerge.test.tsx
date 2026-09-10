import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import DietComponentMergePage from "./DietComponentMerge";

const mockApiFetch = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

const emptyBoard = { date: "2026-09-10", meals: [], diets: [], merged: [] };

// Default (10.9.2026) je "spolu" — bez výnimiek sú OBIDVE zložky v `merged`.
const boardAllSpolu = {
  date: "2026-09-10",
  meals: [
    {
      meal: "main_course",
      label: "Hlavný chod",
      template_name: "Obed A",
      components: [
        { index: 0, label: "Hlavná časť" },
        { index: 1, label: "Príloha" },
      ],
    },
  ],
  diets: [{ id: 1, name: "Bez lepku" }],
  merged: [
    { meal: "main_course", diet_name: "Bez lepku", component_index: 0 },
    { meal: "main_course", diet_name: "Bez lepku", component_index: 1 },
  ],
};

// Index 0 chýba v `merged` → je to dnešná výnimka "zvlášť".
const boardWithOneException = {
  ...boardAllSpolu,
  merged: [{ meal: "main_course", diet_name: "Bez lepku", component_index: 1 }],
};

// Obe zložky chýbajú v `merged` → obe sú "zvlášť" (žiadny default zlúčený).
const boardBothSeparate = { ...boardAllSpolu, merged: [] };

beforeEach(() => {
  mockApiFetch.mockReset();
});

describe("DietComponentMergePage", () => {
  it("shows an empty state when the day has no meal plan", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => emptyBoard });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(
      await screen.findByText(/jedálniček pre tento deň ešte nie je nastavený/i)
    ).toBeInTheDocument();
  });

  it("collapses a meal section by default when everything is spolu today", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => boardAllSpolu });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(await screen.findByText("Hlavný chod")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rozbaliť/i })).toBeInTheDocument();
    expect(screen.getByText(/dnes všetko spolu/i)).toBeInTheDocument();
    expect(screen.queryByText("Hlavná časť")).not.toBeInTheDocument();
    expect(screen.queryByText("Bez lepku")).not.toBeInTheDocument();
  });

  it("expands a collapsed meal section on click, revealing the grid checked as spolu by default", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => boardAllSpolu });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));

    expect(await screen.findByText("Hlavná časť")).toBeInTheDocument();
    expect(screen.getByText("Príloha")).toBeInTheDocument();
    expect(screen.getByText("Bez lepku")).toBeInTheDocument();
    expect(screen.getAllByText("spolu")).toHaveLength(2);
    expect(screen.queryByText("zvlášť")).not.toBeInTheDocument();
  });

  it("expands a meal section by default when it has an exception (zvlášť) today", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => boardWithOneException,
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(await screen.findByText("spolu")).toBeInTheDocument();
    expect(screen.getByText("zvlášť")).toBeInTheDocument();
    expect(screen.getByText(/1 zvlášť/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zbaliť/i })).toBeInTheDocument();
  });

  it("highlights a merged (spolu) cell with a distinct background from a separate one", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => boardWithOneException,
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    const mergedCell = (await screen.findByText("spolu")).closest("td");
    const separateCell = screen.getByText("zvlášť").closest("td");
    expect(mergedCell?.style.background).not.toBe("");
    expect(mergedCell?.style.background).not.toBe(separateCell?.style.background);
  });

  it("shows the diet name in its own configured text/background color", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardAllSpolu,
        diets: [
          {
            id: 1,
            name: "Bez lepku",
            base_diet_names: [],
            text_color: "#123456",
            background_color: "#abcdef",
          },
        ],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));
    const nameCell = (await screen.findByText("Bez lepku")).closest("td");
    expect(nameCell?.style.color).toBe("rgb(18, 52, 86)");
    expect(nameCell?.style.background).toBe("rgb(171, 205, 239)");
  });

  it("locks a composite diet's cell until every one of its base diets is merged there", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardBothSeparate,
        diets: [
          { id: 1, name: "NoMilk", base_diet_names: [] },
          { id: 2, name: "NoMilk+Bez lepku", base_diet_names: ["NoMilk", "Bez lepku"] },
        ],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    // Board je celý "zvlášť" (žiadny default spolu) — sekcia sa rozbalí sama.
    await screen.findByText("NoMilk+Bez lepku");
    const buttons = screen.getAllByText("zvlášť").map((el) => el.closest("button"));
    // Riadok NoMilk (bez base) je klikateľný, riadok kombinácie (chýbajú obe
    // základné diéty) je uzamknutý — celý riadok kombinácie má disabled tlačidlá.
    const noMilkButtons = buttons.slice(0, 2);
    const comboButtons = buttons.slice(2, 4);
    expect(noMilkButtons.every((b) => !b?.disabled)).toBe(true);
    expect(comboButtons.every((b) => b?.disabled)).toBe(true);
  });

  it("unlocks a composite diet's cell once all its base diets are merged there", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardAllSpolu,
        diets: [
          { id: 1, name: "NoMilk", base_diet_names: [] },
          { id: 2, name: "Bez lepku", base_diet_names: [] },
          { id: 3, name: "NoMilk+Bez lepku", base_diet_names: ["NoMilk", "Bez lepku"] },
        ],
        merged: [
          { meal: "main_course", diet_name: "NoMilk", component_index: 0 },
          { meal: "main_course", diet_name: "Bez lepku", component_index: 0 },
        ],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    await screen.findByText("NoMilk+Bez lepku");
    const comboRow = screen.getByText("NoMilk+Bez lepku").closest("tr");
    const comboFirstCellButton = comboRow?.querySelectorAll("button")[0];
    expect(comboFirstCellButton?.disabled).toBe(false);
  });

  it("surfaces the server's rejection message when a toggle is refused", async () => {
    mockApiFetch.mockResolvedValueOnce({ ok: true, json: async () => boardBothSeparate });
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "Kombinovaná diéta „X“ môže byť spolu, až keď…" }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    // Board je celý "zvlášť" — sekcia sa rozbalí sama.
    const buttons = await screen.findAllByText("zvlášť");
    fireEvent.click(buttons[0]);

    expect(await screen.findByText(/kombinovaná diéta „x“/i)).toBeInTheDocument();
  });

  it("clicking a zvlášť cell POSTs a toggle with the right key and applies the refreshed board", async () => {
    mockApiFetch.mockResolvedValueOnce({ ok: true, json: async () => boardBothSeparate });
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => boardWithOneException,
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    // Board je celý "zvlášť" — sekcia sa rozbalí sama.
    const buttons = await screen.findAllByText("zvlášť");
    fireEvent.click(buttons[1]);

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2));
    const [url, options] = mockApiFetch.mock.calls[1];
    expect(String(url)).toContain("/admin/diet-component-merge/toggle/");
    const body = JSON.parse((options as RequestInit).body as string);
    expect(body).toMatchObject({
      meal: "main_course",
      component_index: 1,
      diet_id: 1,
      merged: true,
    });

    await waitFor(() => expect(screen.getByText("spolu")).toBeInTheDocument());
  });

  it("clicking a spolu cell POSTs merged:false (marks zvlášť) and checks the box", async () => {
    mockApiFetch.mockResolvedValueOnce({ ok: true, json: async () => boardAllSpolu });
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => boardWithOneException,
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));
    const buttons = await screen.findAllByText("spolu");
    fireEvent.click(buttons[0]);

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2));
    const [, options] = mockApiFetch.mock.calls[1];
    const body = JSON.parse((options as RequestInit).body as string);
    expect(body).toMatchObject({
      meal: "main_course",
      component_index: 0,
      diet_id: 1,
      merged: false,
    });
  });

  it("checkbox is unchecked by default for spolu and checked for the zvlášť exception", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => boardWithOneException,
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    const spoluButton = (await screen.findByText("spolu")).closest("button");
    const zvlastButton = screen.getByText("zvlášť").closest("button");
    expect(spoluButton?.className).not.toMatch(/\bon\b/);
    expect(zvlastButton?.className).toMatch(/\bon\b/);
  });

  it("filters diet rows in a meal section by the search box", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardAllSpolu,
        diets: [
          { id: 1, name: "Bez lepku" },
          { id: 2, name: "Bez laktózy" },
        ],
        merged: [
          { meal: "main_course", diet_name: "Bez lepku", component_index: 0 },
          { meal: "main_course", diet_name: "Bez lepku", component_index: 1 },
          { meal: "main_course", diet_name: "Bez laktózy", component_index: 0 },
          { meal: "main_course", diet_name: "Bez laktózy", component_index: 1 },
        ],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));
    await screen.findByText("Bez lepku");
    expect(screen.getByText("Bez laktózy")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/hľadať diétu/i), {
      target: { value: "lepku" },
    });

    expect(screen.getByText("Bez lepku")).toBeInTheDocument();
    expect(screen.queryByText("Bez laktózy")).not.toBeInTheDocument();
  });
});
