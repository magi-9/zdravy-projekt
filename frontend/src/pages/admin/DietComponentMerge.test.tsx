import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import DietComponentMergePage from "./DietComponentMerge";

const mockApiFetch = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

const emptyBoard = { date: "2026-09-10", meals: [], diets: [], merged: [] };

const boardWithMainCourse = {
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
  merged: [],
};

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

  it("collapses a meal section by default when it has no merges today", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => boardWithMainCourse });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(await screen.findByText("Hlavný chod")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rozbaliť/i })).toBeInTheDocument();
    expect(screen.queryByText("Hlavná časť")).not.toBeInTheDocument();
    expect(screen.queryByText("Bez lepku")).not.toBeInTheDocument();
  });

  it("expands a collapsed meal section on click, revealing the grid unchecked by default", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => boardWithMainCourse });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));

    expect(await screen.findByText("Hlavná časť")).toBeInTheDocument();
    expect(screen.getByText("Príloha")).toBeInTheDocument();
    expect(screen.getByText("Bez lepku")).toBeInTheDocument();
    expect(screen.getAllByText("zvlášť")).toHaveLength(2);
    expect(screen.queryByText("spolu")).not.toBeInTheDocument();
  });

  it("expands a meal section by default when it already has a merge today", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardWithMainCourse,
        merged: [{ meal: "main_course", diet_name: "Bez lepku", component_index: 0 }],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(await screen.findByText("spolu")).toBeInTheDocument();
    expect(screen.getByText("zvlášť")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zbaliť/i })).toBeInTheDocument();
  });

  it("highlights a merged cell with a distinct background from a separate one", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardWithMainCourse,
        merged: [{ meal: "main_course", diet_name: "Bez lepku", component_index: 0 }],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    const mergedCell = (await screen.findByText("spolu")).closest("td");
    const separateCell = screen.getByText("zvlášť").closest("td");
    expect(mergedCell?.style.background).not.toBe("");
    expect(mergedCell?.style.background).not.toBe(separateCell?.style.background);
  });

  it("clicking a cell POSTs a toggle with the right key and applies the refreshed board", async () => {
    mockApiFetch.mockResolvedValueOnce({ ok: true, json: async () => boardWithMainCourse });
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...boardWithMainCourse,
        merged: [{ meal: "main_course", diet_name: "Bez lepku", component_index: 0 }],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /rozbaliť/i }));
    const buttons = await screen.findAllByText("zvlášť");
    fireEvent.click(buttons[0]);

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2));
    const [url, options] = mockApiFetch.mock.calls[1];
    expect(String(url)).toContain("/admin/diet-component-merge/toggle/");
    const body = JSON.parse((options as RequestInit).body as string);
    expect(body).toMatchObject({
      meal: "main_course",
      component_index: 0,
      diet_id: 1,
      merged: true,
    });

    await waitFor(() => expect(screen.getByText("spolu")).toBeInTheDocument());
  });
});
