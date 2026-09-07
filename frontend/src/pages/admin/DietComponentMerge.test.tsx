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

  it("renders one column per component and one row per diet, unchecked by default", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => boardWithMainCourse });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    expect(await screen.findByText("Hlavná časť")).toBeInTheDocument();
    expect(screen.getByText("Príloha")).toBeInTheDocument();
    expect(screen.getByText("Bez lepku")).toBeInTheDocument();
    expect(screen.getAllByText("zvlášť")).toHaveLength(2);
    expect(screen.queryByText("spolu")).not.toBeInTheDocument();
  });

  it("shows already-merged components as checked", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...boardWithMainCourse,
        merged: [{ meal: "main_course", diet_name: "Bez lepku", component_index: 0 }],
      }),
    });

    render(<MemoryRouter><DietComponentMergePage /></MemoryRouter>);

    await screen.findByText("Hlavná časť");
    expect(screen.getByText("spolu")).toBeInTheDocument();
    expect(screen.getByText("zvlášť")).toBeInTheDocument();
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
