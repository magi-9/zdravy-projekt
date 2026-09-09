import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import PrevadzkaOverview from "./PrevadzkaOverview";

const mockApiFetch = vi.fn();
// Module-level (not per-call) — the real `useToast()` memoizes these with
// `useCallback`, so a fresh `vi.fn()` on every render here would destabilize
// any consumer's dependency arrays (e.g. `fetchData`'s `[apiFetch, date,
// toastError]`) in a way the real hook never does, causing spurious re-fetch
// loops under sustained interaction (found via #563 attention popover tests).
const mockToastError = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastWarning = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

vi.mock("../../context/ToastContext", () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
    warning: mockToastWarning,
  }),
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

  it("shows source-specific ZV state and an OL badge only for afternoon snack with lunch", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-08-10",
        edupage: [{
          ...baseRow,
          nazov: "Edu škola",
          adults_pack_separately_enabled: true,
          pack_separately_enabled: false,
          olovrant_s_obedom: true,
          flags: { attention: [], config_notes: [] },
        }],
        app: [{
          ...baseRow,
          prevadzka_id: 2,
          nazov: "App škola",
          adults_pack_separately_enabled: false,
          pack_separately_enabled: false,
          olovrant_s_obedom: false,
          flags: { attention: [], config_notes: [] },
        }],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);

    expect(await screen.findByLabelText("EduPage: dospelí automaticky zvlášť — zapnuté")).toHaveClass("on");
    expect(screen.getByLabelText("App: zabaliť zvlášť — vypnuté")).toHaveClass("off");
    const olBadge = screen.getByLabelText("Olovrant sa vozí s obedom");
    expect(olBadge).toHaveTextContent("OL");
    // Dva príznaky nesmú roztlačiť začiatok názvu prevádzky doprava oproti
    // riadkom s jedným príznakom — majú spoločný stĺpec a idú pod seba.
    expect(olBadge.parentElement).toHaveClass("zpa-ovflags--stacked");
    expect(document.querySelector("#prevadzka-row-2 [aria-label='Olovrant sa vozí s obedom']")).toBeNull();
  });

  it("shows attention notes in a hover popover, with a dismiss button that posts to the API", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (String(url).includes("dismiss-attention")) {
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return {
        ok: true,
        json: async () => ({
          date: "2026-09-09",
          edupage: [
            {
              ...baseRow,
              attention_dismissed: false,
              flags: {
                attention: ["S:sA — patrí Stromčeku, over/rozdeľ appkové objednávky (4)"],
                config_notes: [],
                unmapped_diets: [],
                uncertain_diets: [],
              },
            },
          ],
          app: [],
        }),
      };
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);
    await screen.findByText("MŠ Testovacia");
    const input = (await screen.findByDisplayValue(/^\d{4}-\d{2}-\d{2}$/)) as HTMLInputElement;
    const shownDate = input.value;

    // Popup content is hidden until hover.
    expect(screen.queryByText(/patrí Stromčeku/)).not.toBeInTheDocument();

    const dot = document.querySelector(".zpa-attnpop") as HTMLElement;
    fireEvent.mouseEnter(dot);

    expect(await screen.findByText(/patrí Stromčeku/)).toBeInTheDocument();
    const dismissBtn = screen.getByRole("button", { name: /OK, vybavené/i });

    fireEvent.click(dismissBtn);

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/admin/summary/dismiss-attention/"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ prevadzka_id: 1, date: shownDate }),
        }),
      ),
    );
  });

  it("hides the dismiss button once attention_dismissed is already true", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-09-09",
        edupage: [
          {
            ...baseRow,
            attention_dismissed: true,
            flags: {
              attention: ["S:sA — over"],
              config_notes: [],
              unmapped_diets: [],
              uncertain_diets: [],
            },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);
    await screen.findByText("MŠ Testovacia");

    const dot = document.querySelector(".zpa-attnpop") as HTMLElement;
    fireEvent.mouseEnter(dot);

    await screen.findByText(/vybavené/);
    expect(screen.queryByRole("button", { name: /OK, vybavené/i })).not.toBeInTheDocument();
  });

  it("offers a dismiss button for config_notes-only flags too (not just attention)", async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        date: "2026-09-09",
        edupage: [
          {
            ...baseRow,
            attention_dismissed: false,
            flags: {
              attention: [],
              config_notes: ["olovrant chýba"],
              unmapped_diets: [],
              uncertain_diets: [],
            },
          },
        ],
        app: [],
      }),
    });

    render(<MemoryRouter><PrevadzkaOverview /></MemoryRouter>);
    await screen.findByText("MŠ Testovacia");

    const dot = document.querySelector(".zpa-attnpop") as HTMLElement;
    fireEvent.mouseEnter(dot);

    await screen.findByText("olovrant chýba");
    expect(screen.getByRole("button", { name: /OK, vybavené/i })).toBeInTheDocument();
  });
});
