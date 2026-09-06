import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import PrevadzkaOverview from "./PrevadzkaOverview";

const mockApiFetch = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

vi.mock("../../context/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

describe("PrevadzkaOverview", () => {
  it("does not offer PDF or XLSX export", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ date: "2026-08-10", edupage: [], app: [] }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    await screen.findByText("Kontrola objednávok");
    expect(screen.queryByRole("button", { name: /PDF/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /XLSX/i })).not.toBeInTheDocument();
    expect(mockApiFetch.mock.calls.every(([url]) => !String(url).includes("-xlsx") && !String(url).includes("-pdf"))).toBe(true);
  });

  it("defaults the date picker to a weekday, never a weekend", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ date: "2026-08-10", edupage: [], app: [] }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    const input = await screen.findByDisplayValue(/^\d{4}-\d{2}-\d{2}$/);
    const [year, month, day] = (input as HTMLInputElement).value.split("-").map(Number);
    const weekday = new Date(year, month - 1, day).getDay();
    expect(weekday).not.toBe(0);
    expect(weekday).not.toBe(6);
  });

  const baseRow = {
    prevadzka_id: 1,
    nazov: "MŠ Testovacia",
    celok: "MŠ Testovacia",
    delivered: true,
    delivery_status: "manual" as const,
    counts: { breakfast: 0, lunch: 5, olovrant: 0, total: 5 },
    has_warning: true,
  };

  it("shows unmapped diets inline, not just in a hover tooltip", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-08-10",
        edupage: [
          {
            ...baseRow,
            flags: { attention: [], config_notes: [], unmapped_diets: ["N:NO KAKAO"] },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    expect(await screen.findByText(/NO KAKAO/)).toBeInTheDocument();
  });

  it("shows uncertain (fuzzy-matched) diets inline", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-08-10",
        edupage: [
          {
            ...baseRow,
            flags: {
              attention: [],
              config_notes: [],
              unmapped_diets: [],
              uncertain_diets: ["Z:XYZ→NO MILK"],
            },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    expect(await screen.findByText(/XYZ→NO MILK/)).toBeInTheDocument();
  });

  it("shows classic count and per-diet breakdown below the row, separate from the delivery total", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-08-10",
        edupage: [
          {
            ...baseRow,
            counts: {
              breakfast: 0,
              lunch: 5,
              olovrant: 0,
              total: 5,
              standard_total: 3,
              diet_counts: { "Bezlaktózová": 2 },
            },
            flags: { attention: [], config_notes: [], unmapped_diets: [], uncertain_diets: [] },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    await screen.findByText("MŠ Testovacia");
    expect(screen.getByText("klasik 3, Bezlaktózová 2")).toBeInTheDocument();
    // "Spolu" (celkový počet na rozvoz) ostáva nedotknuté, vrátane detí s diétou.
    expect(screen.getAllByText("5").length).toBeGreaterThan(0);
  });

  it("does not render an extra warning line when there are no diet flags", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-08-10",
        edupage: [
          {
            ...baseRow,
            has_warning: false,
            flags: { attention: [], config_notes: [], unmapped_diets: [], uncertain_diets: [] },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    await screen.findByText("MŠ Testovacia");
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });
});
