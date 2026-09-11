import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage";

const mockApiFetch = vi.fn();

vi.mock("../../../hooks/useIsPC", () => ({
  useIsPC: () => true,
}));

const mockPrevadzky: { id: number; nazov: string }[] = [];

vi.mock("../context/AppContext", () => ({
  useApp: () => ({
    globalDeadlines: {
      breakfast: "10:00",
      breakfast_day_before: false,
      lunch: "10:00",
      lunch_day_before: false,
      olovrant: "10:00",
      olovrant_day_before: false,
    },
    activePrevadzka: mockPrevadzky.length === 1 ? mockPrevadzky[0] : null,
    prevadzky: mockPrevadzky,
  }),
}));

// Stabilná identita: HomePage má `user` v deps efektov, nový objekt pri každom
// renderi by fetch spúšťal donekonečna a uzly by sa odpájali spod assertov.
const mockUser = { email: "test@example.com" };
const mockAuth = { apiFetch: mockApiFetch, user: mockUser };

vi.mock("../../../context/auth", () => ({
  useAuth: () => mockAuth,
}));

vi.mock("../../../context/ToastContext", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  }),
}));

// Stub namiesto celého modalu: testy histórie ho nepotrebujú, ale vynulovanie
// sa inak nedá spustiť — `onZero` visí len na ňom.
vi.mock("../components/order/OrderSummaryModal", () => ({
  default: ({
    isOpen,
    onZero,
  }: {
    isOpen?: boolean;
    onZero?: () => void;
  }) =>
    isOpen && onZero ? (
      <button data-testid="zero-order" onClick={onZero}>
        Vynulovať
      </button>
    ) : null,
}));

vi.mock("../components/onboarding/TourOverlay", () => ({
  default: () => null,
}));

describe("HomePage history", () => {
  afterEach(() => {
    cleanup();
    mockPrevadzky.length = 0;
    localStorage.clear();
  });

  it("renders concrete ordered diet names in history", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/orders/planned/monthly-summary/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 0, items: [] }) });
      }
      if (url.endsWith("/orders/planned/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith("/orders/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                date: "2026-07-22",
                status: "submitted",
                data: {
                  lunch: {
                    "Škôlka": {
                      menuCounts: { A: 2 },
                      diets: { "Bez lepku": 1, Vegánske: 0 },
                    },
                  },
                  olovrant: {
                    "Predškolák": {
                      menuCounts: { A: 1 },
                      diets: { "Bez laktózy": 2 },
                    },
                  },
                },
              },
            ]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Škôlka · Bez lepku · 1x")).toBeInTheDocument();
      expect(screen.getByText("Predškolák · Bez laktózy · 2x")).toBeInTheDocument();
    });
  });

  it("sums a day across the celok and breaks it down per prevádzka on click", async () => {
    mockPrevadzky.push({ id: 1, nazov: "Škôlka Sever" }, { id: 2, nazov: "Škôlka Juh" });

    const order = (prevadzka: number, category: string, count: number, diet: string) => ({
      date: "2026-07-22",
      status: "submitted",
      prevadzka,
      data: { lunch: { [category]: { menuCounts: { A: count }, diets: { [diet]: 1 } } } },
    });

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/orders/planned/monthly-summary/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 0, items: [] }) });
      }
      if (url.endsWith("/orders/planned/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith("/orders/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              order(1, "Škôlka", 4, "Bez lepku"),
              order(2, "Jasle", 3, "Bez laktózy"),
            ]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    // Zbalený riadok: jeden deň, súčet za celý celok (4 + 3), bez rozpisu.
    const summary = await screen.findByText("2 prevádzky · zobraz rozpis");
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("Škôlka Sever")).not.toBeInTheDocument();

    const dayRow = summary.closest('[role="button"]');
    expect(dayRow).not.toBeNull();
    fireEvent.click(dayRow!);

    // Rozbalené: každá prevádzka so svojím počtom a diétami.
    expect(await screen.findByText("Škôlka Sever")).toBeInTheDocument();
    expect(screen.getByText("Škôlka Juh")).toBeInTheDocument();
    expect(screen.getByText("Škôlka · Bez lepku · 1x")).toBeInTheDocument();
    expect(screen.getByText("Jasle · Bez laktózy · 1x")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("zeroes a predicted day for every prevádzka of the celok", async () => {
    mockPrevadzky.push({ id: 7, nazov: "Sever" }, { id: 9, nazov: "Juh" });

    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const posts: unknown[] = [];

    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/orders/") && init?.method === "POST") {
        posts.push(JSON.parse(String(init.body)));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      if (url.includes("/orders/planned/monthly-summary/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 0, items: [] }) });
      }
      if (url.endsWith("/orders/planned/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                date: today,
                exists: false,
                is_auto: null,
                is_empty: null,
                totalPortions: 0,
                mealCount: { breakfast: 0, lunch: 0, olovrant: 0 },
                predictedTotal: 6,
                predictedMealCount: { breakfast: 0, lunch: 6, olovrant: 0 },
                predictedData: { lunch: { "Škôlka": { menuCounts: { A: 6 }, diets: {} } } },
              },
            ]),
        });
      }
      if (url.endsWith("/orders/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    // Karta dnešného dňa s predikciou otvorí modal vynulovania.
    const todayCard = await screen.findByText("Dnešná objednávka");
    fireEvent.click(todayCard.closest(".zp-section")!.querySelector('[role="button"]')!);

    fireEvent.click(await screen.findByTestId("zero-order"));

    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts).toEqual([
      expect.objectContaining({ date: today, prevadzka: 7, status: "submitted" }),
      expect.objectContaining({ date: today, prevadzka: 9, status: "submitted" }),
    ]);
    // Jarabinka 11.9.2026: explicitné vynulovanie musí označiť všetky tri
    // jedlá ako touched, inak auto-order cron doplní "chýbajúci" obed
    // šablónou z predošlého dňa napriek tomu, že klient chcel nulu.
    for (const post of posts) {
      expect(post).toMatchObject({
        touched_meals: ["breakfast", "lunch", "olovrant"],
      });
    }
  });
});
