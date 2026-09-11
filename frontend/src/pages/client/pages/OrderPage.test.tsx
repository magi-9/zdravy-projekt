import { describe, it, expect, vi, beforeEach, afterEach, Mock } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import "@testing-library/jest-dom";
import OrderPage from "./OrderPage";
import { buildPackSeparatelyItems } from "../components/order/packSeparately";
import { AppProvider, useApp } from "../context/AppContext";
import { MemoryRouter } from "react-router-dom";
import OrderService from "../services/OrderService";
import { ReactNode } from "react";
import { ToastProvider } from "../../../context/ToastContext";
import { useAuth } from "../../../context/auth";
import { stepBusinessDay, fromDateKey, toDateKey } from "../../../lib/businessDay";

const mockApiFetch = vi.fn();
const mockUser = { id: 1, email: "client@example.com" };

const makeMockResponse = (payload: unknown, ok = true) => ({
  ok,
  json: () => Promise.resolve(payload),
  text: () => Promise.resolve(typeof payload === "string" ? payload : JSON.stringify(payload)),
  clone() {
    return makeMockResponse(payload, ok);
  },
});

// Mock Auth Context
vi.mock("../../../context/auth", () => ({
  useAuth: vi.fn(() => ({
    logout: vi.fn(),
    apiFetch: mockApiFetch,
    user: mockUser,
  })),
  AuthProvider: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

// Mock OnboardingContext
vi.mock("../../../context/OnboardingContext", () => ({
  useOnboarding: vi.fn(() => ({
    isTourActive: false,
    currentStep: 0,
    totalSteps: 9,
    startTour: vi.fn(),
    nextStep: vi.fn(),
    prevStep: vi.fn(),
    completeTour: vi.fn(),
    skipTour: vi.fn(),
    resetTour: vi.fn(),
  })),
  OnboardingProvider: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

// Mock OrderService with implementation that allows actual data structure usage
vi.mock("../services/OrderService", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../services/OrderService")>();
  const originalDefault = actual.default;

  // Statické metódy triedy sú non-enumerable, takže spread by ich nepreniesol,
  // a ručný zoznam sa rozbije vždy, keď v OrderService pribudne interná metóda
  // volaná cez `this` (napr. withClampedPackSeparately). Preto ich prenesieme
  // všetky a naviažeme na originál — mockujeme len to, čo naozaj treba.
  const bound: Record<string, unknown> = {};
  let proto: unknown = originalDefault;
  while (proto && proto !== Function.prototype && proto !== Object.prototype) {
    for (const key of Object.getOwnPropertyNames(proto)) {
      if (key in bound) continue;
      const value = (originalDefault as unknown as Record<string, unknown>)[key];
      bound[key] = typeof value === "function"
        ? (value as (...args: unknown[]) => unknown).bind(originalDefault)
        : value;
    }
    proto = Object.getPrototypeOf(proto);
  }

  return {
    default: {
      ...bound,
      checkDeadline: vi.fn(),
      getAvailableDiets: vi.fn().mockReturnValue(["Bezlepková", "Diabetická"]),
      getAvailableDietsWithSpecial: vi.fn().mockReturnValue(["Bezlepková", "Diabetická"]),
    },
  };
});

// Use local date (not UTC) to match what useOrder's selectedDate key uses.
const localDateStr = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

describe("buildPackSeparatelyItems", () => {
  const category = "Škôlka";
  const build = (
    menuCount: number,
    diets: Record<string, number>,
    dietMenuVariantMap: Record<string, string>,
  ) => buildPackSeparatelyItems({
    [category]: {
      menuCounts: { A: menuCount },
      diets,
      packSeparately: { menus: {}, diets: {} },
    },
  }, [category], dietMenuVariantMap);

  it("fully merges equal linked menu and diet counts", () => {
    expect(build(2, { "Veggie/No Fish": 2 }, { "Veggie/No Fish": "A" })).toEqual([{
      category,
      kind: "menus",
      keyName: "A",
      linkedDietKey: "Veggie/No Fish",
      linkedRow: "merged",
      orderedCount: 2,
      count: 0,
      target: "zvlast",
    }]);
  });

  it("splits a linked menu into the overlapping portion and plain remainder", () => {
    expect(build(5, { "Veggie/No Fish": 2 }, { "Veggie/No Fish": "A" })).toEqual([
      {
        category,
        kind: "menus",
        keyName: "A",
        linkedDietKey: "Veggie/No Fish",
        linkedRow: "merged",
        orderedCount: 2,
        count: 0,
        target: "zvlast",
      },
      {
        category,
        kind: "menus",
        keyName: "A",
        linkedDietKey: "Veggie/No Fish",
        linkedRow: "remainder",
        orderedCount: 3,
        count: 0,
        target: "zvlast",
      },
    ]);
  });

  it("leaves an unlinked diet as its own row", () => {
    expect(build(2, { "Špeciálna": 1 }, { "Veggie/No Fish": "A" })).toEqual([
      {
        category,
        kind: "menus",
        keyName: "A",
        orderedCount: 2,
        count: 0,
        target: "zvlast",
      },
      {
        category,
        kind: "diets",
        keyName: "Špeciálna",
        orderedCount: 1,
        count: 0,
        menuVariant: undefined,
        target: "zvlast",
      },
    ]);
  });
});

describe("OrderPage Logic & Triggers", () => {
  // Helper to interact with real localStorage in tests
  const localStorageMock = (function () {
    let store: Record<string, string> = {};
    return {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = value.toString();
      },
      clear: () => {
        store = {};
      },
      removeItem: (key: string) => {
        delete store[key];
      },
    };
  })();

  Object.defineProperty(window, "localStorage", { value: localStorageMock });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    // AppProvider si vybranú prevádzku pamätá v sessionStorage cez celý beh súboru.
    sessionStorage.clear();
    (OrderService.checkDeadline as Mock).mockReturnValue(true);
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(
          makeMockResponse({
            deadline_breakfast: "10:00",
            deadline_breakfast_is_day_before: false,
            deadline_lunch: "10:00",
            deadline_lunch_is_day_before: false,
            deadline_olovrant: "10:00",
            deadline_olovrant_is_day_before: false,
          }),
        );
      }

      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({ id: 1, status: "draft", data: {} }),
        );
      }

      if (url.includes("/orders/") && init?.method === "POST") {
        return Promise.resolve(makeMockResponse({}));
      }

      return Promise.resolve(makeMockResponse([]));
    });

    // Setup default settings to avoid auto-trigger interference unless tested
    localStorageMock.setItem(
      "appSettings",
      JSON.stringify({
        copyBreakfastFromPrevLunch: false,
        copyOlovrantFromLunch: false,
        applyDefaultLunch: false,
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPage = (showMealPlanAvailability = false, initialEntries: string[] = ["/order"]) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <ToastProvider>
          <AppProvider>
            <OrderPage />
            {showMealPlanAvailability && <MealPlanAvailabilityProbe />}
          </AppProvider>
        </ToastProvider>
      </MemoryRouter>,
    );
  };

  const MealPlanAvailabilityProbe = () => {
    const { mealPlanAvailability } = useApp();
    const serialized = mealPlanAvailability === null
      ? "none"
      : JSON.stringify(Object.fromEntries(
          Object.entries(mealPlanAvailability).map(([meal, variants]) => [meal, [...variants]]),
        ));
    return <output data-testid="meal-plan-availability">{serialized}</output>;
  };

  const getOrderData = (date: string) => {
    const data = localStorageMock.getItem(`order_${date}`);
    return data ? JSON.parse(data) : null;
  };

  const getMealCard = (title: string) => {
    // Text „Raňajky“ sa vyskytuje aj mimo karty, takže sa nedá brať prvý zásah —
    // hľadáme kartu, ktorej vlastný .zp-meal-title sedí.
    const cards = Array.from(document.querySelectorAll<HTMLElement>(".zp-meal"));
    const card = cards.find(
      (c) => c.querySelector(".zp-meal-title")?.textContent?.trim() === title,
    );
    if (!card) throw new Error(`Meal card "${title}" not found`);
    return card;
  };

  const getCategoryRow = (card: HTMLElement, category: string) => {
    const rows = Array.from(card.querySelectorAll<HTMLElement>(".zp-cat"));
    const row = rows.find(
      (r) => r.querySelector(".zp-cat-head")?.textContent?.trim() === category,
    );
    if (!row) throw new Error(`Category "${category}" not found in card`);
    return row;
  };

  /**
   * Prevádzku vracia len test, ktorý ju naozaj potrebuje. Keby ju vracal
   * zdieľaný mock, `scopedKey` by localStorage kľúče začal scopovať podľa
   * prevádzky a všetky ostatné testy by si prestali nájsť nasadené dáta.
   */
  const mockPrevadzkaWithPerMealMenus = () => {
    const original = mockApiFetch.getMockImplementation()!;
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/prevadzky/")) {
        return Promise.resolve(
          makeMockResponse([
            {
              id: 11,
              nazov: "Test prevádzka",
              adresa: "",
              celok: "Test celok",
              visible_menus: ["A", "B", "C", "V"],
              visible_meals: ["breakfast", "lunch", "olovrant"],
              pack_separately_enabled: false,
            },
          ]),
        );
      }
      return original(url, init);
    });
  };

  const mockPrevadzkaPortionVisibility = (
    visiblePortionTypes?: Array<{ id: number; name: string }>,
  ) => {
    const original = mockApiFetch.getMockImplementation()!;
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/prevadzky/")) {
        return Promise.resolve(makeMockResponse([{
          id: 12,
          nazov: "Porciová prevádzka",
          adresa: "",
          celok: "Test celok",
          visible_menus: ["A", "B", "C", "V"],
          visible_meals: ["breakfast", "lunch", "olovrant"],
          visible_portion_types: visiblePortionTypes,
          visible_diets: [],
          pack_separately_enabled: false,
        }]));
      }
      if (url.includes("/admin/portion-types/")) {
        return Promise.resolve(makeMockResponse([
          { id: 1, name: "Jasle", is_active: true },
          { id: 2, name: "Škôlka", is_active: true },
        ]));
      }
      return original(url, init);
    });
  };

  it("shows only portion types visible for the active prevádzka", async () => {
    mockPrevadzkaPortionVisibility([{ id: 2, name: "Škôlka" }]);

    renderPage();

    await waitFor(() => {
      expect(within(getMealCard("Obed")).getByText("Škôlka")).toBeInTheDocument();
    });
    expect(within(getMealCard("Obed")).queryByText("Jasle")).not.toBeInTheDocument();
  });

  it("shows all portion types when visibility is missing", async () => {
    mockPrevadzkaPortionVisibility();

    renderPage();

    await waitFor(() => {
      expect(within(getMealCard("Obed")).getByText("Jasle")).toBeInTheDocument();
      expect(within(getMealCard("Obed")).getByText("Škôlka")).toBeInTheDocument();
    });
  });

  it("shows all portion types when visibility is an empty list (not yet backfilled)", async () => {
    mockPrevadzkaPortionVisibility([]);

    renderPage();

    await waitFor(() => {
      expect(within(getMealCard("Obed")).getByText("Jasle")).toBeInTheDocument();
      expect(within(getMealCard("Obed")).getByText("Škôlka")).toBeInTheDocument();
    });
  });

  /** Celok s dvoma prevádzkami (napr. Šidielko + tučniačik) → klient musí vyberať. */
  const mockTwoPrevadzky = () => {
    const original = mockApiFetch.getMockImplementation()!;
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/prevadzky/")) {
        return Promise.resolve(makeMockResponse(
          [
            { id: 21, nazov: "Šidielko", adresa: "Cablkova 6" },
            { id: 22, nazov: "tučniačik", adresa: "Cablkova 6" },
          ].map((p) => ({
            ...p,
            celok: "Šidielko",
            visible_menus: ["A", "B", "C", "V"],
            visible_meals: ["breakfast", "lunch", "olovrant"],
            visible_diets: [],
            pack_separately_enabled: false,
          })),
        ));
      }
      return original(url, init);
    });
  };

  it("lets the client switch prevádzka after the first choice", async () => {
    mockTwoPrevadzky();

    renderPage();

    // Najprv chooser…
    const sidielko = await screen.findByRole("button", { name: /Šidielko/ });
    fireEvent.click(sidielko);

    // …potom je v objednávke vidieť, za koho sa hlási.
    const strip = await screen.findByText("Objednávate za");
    expect(strip.parentElement).toHaveTextContent("Šidielko");

    // A dá sa prepnúť späť na výber — toto predtým chýbalo a výber ostal zaseknutý.
    fireEvent.click(screen.getByRole("button", { name: "Zmeniť" }));
    fireEvent.click(await screen.findByRole("button", { name: /tučniačik/ }));

    await waitFor(() => {
      expect(screen.getByText("Objednávate za").parentElement).toHaveTextContent("tučniačik");
    });
  });

  it("remembers the chosen prevádzka across a remount (page refresh)", async () => {
    mockTwoPrevadzky();

    const { unmount } = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /tučniačik/ }));
    await screen.findByText("Objednávate za");
    unmount();

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Objednávate za").parentElement).toHaveTextContent("tučniačik");
    });
    expect(screen.queryByText("Za ktorú prevádzku nahlasujete objednávku?")).not.toBeInTheDocument();
  });

  it("drops a stored prevádzka the login no longer has access to", async () => {
    sessionStorage.setItem("chosenPrevadzkaId", "999");
    mockTwoPrevadzky();

    renderPage();

    expect(
      await screen.findByText("Za ktorú prevádzku nahlasujete objednávku?"),
    ).toBeInTheDocument();
  });

  it("Copy Olovrant: Copies data from Lunch when triggered", async () => {
    const date = localDateStr();
    // 1. Seed existing order with Lunch data using VALID category keys (e.g. Škôlka)
    const mockOrder = {
      status: "draft",
      breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      lunch: { Škôlka: { menuCounts: { A: 10 }, diets: {} } },
      olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
    };
    localStorageMock.setItem(`order_${date}`, JSON.stringify(mockOrder));
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: false, lunch: true, olovrant: true }),
    );

    renderPage();

    // 2. Locate Olovrant Card
    const olovrantTitle = screen.getAllByText("Olovrant")[0];
    const olovrantCard = olovrantTitle.closest(".zp-meal");
    expect(olovrantCard).toBeInTheDocument();

    // 3. Find the "Kopírovať z obeda" button in Olovrant card
    const copyBtn = await within(olovrantCard as HTMLElement).findByText(
      /Kopírovať z obeda/i,
    );
    expect(copyBtn).toBeInTheDocument();

    // 4. Click the button
    fireEvent.click(copyBtn);

    // 5. Wait for sync
    await waitFor(() => {
      const updated = getOrderData(date);
      expect(updated.olovrant["Škôlka"].menuCounts["A"]).toBe(10);
    });
  });

  it("Copy Lunch: Copies data from Breakfast when triggered", async () => {
    const date = localDateStr();
    const mockOrder = {
      status: "draft",
      breakfast: { Škôlka: { menuCounts: { A: 8 }, diets: {} } },
      lunch: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
    };
    localStorageMock.setItem(`order_${date}`, JSON.stringify(mockOrder));
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: true, lunch: true, olovrant: false }),
    );

    renderPage();

    const lunchTitle = screen.getAllByText("Obed")[0];
    const lunchCard = lunchTitle.closest(".zp-meal");
    expect(lunchCard).toBeInTheDocument();

    const copyBtn = await within(lunchCard as HTMLElement).findByText(
      /Načítať z raňajok/i,
    );
    fireEvent.click(copyBtn);

    await waitFor(() => {
      const updated = getOrderData(date);
      expect(updated.lunch["Škôlka"].menuCounts["A"]).toBe(8);
    });
  });

  it("typed menu input selects value and empty blur commits 0", async () => {
    const date = localDateStr();
    localStorageMock.setItem(
      `order_${date}`,
      JSON.stringify({
        status: "draft",
        breakfast: { Škôlka: { menuCounts: { A: 2 }, diets: {} } },
        lunch: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
        olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      }),
    );
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: true, lunch: false, olovrant: false }),
    );

    renderPage();

    const breakfastCard = getMealCard("Raňajky");
    // Menu A má každá kategória, tak sa zúžime na tú, ktorú test nasadil.
    const skolkaRow = getCategoryRow(breakfastCard, "Škôlka");
    const input = await within(skolkaRow).findByLabelText("Počet porcií pre menu A");

    fireEvent.focus(input);
    expect((input as HTMLInputElement).selectionStart).toBe(0);
    expect((input as HTMLInputElement).selectionEnd).toBe(String((input as HTMLInputElement).value).length);

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);

    await waitFor(() => {
      expect(getOrderData(date).breakfast["Škôlka"].menuCounts.A).toBe(0);
    });
  });

  it("loads the special diet note saved on the server, not just the local draft", async () => {
    const date = localDateStr();
    // Iný prehliadač/zariadenie ako ten, čo poznámku pôvodne uložil — v
    // localStorage nič nie je, jediný zdroj je server.
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: false, lunch: true, olovrant: false }),
    );
    (OrderService.getAvailableDiets as Mock).mockReturnValue(["Špeciálna"]);
    (OrderService.getAvailableDietsWithSpecial as Mock).mockReturnValue(["Špeciálna"]);

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(makeMockResponse({}));
      }
      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({
            id: 2279,
            status: "submitted",
            data: {
              breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
              lunch: {
                Škôlka: {
                  menuCounts: { A: 15 },
                  diets: { Špeciálna: 2 },
                },
              },
              olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
              special_diet_note: "Alergia na orechy",
            },
          }),
        );
      }
      return Promise.resolve(makeMockResponse([]));
    });

    renderPage();

    const textarea = await screen.findByPlaceholderText(
      "Popíšte vašu špeciálnu diétu",
    );
    await waitFor(() => {
      expect((textarea as HTMLTextAreaElement).value).toBe("Alergia na orechy");
    });
  });

  it("typed diet input has no cap and adds on top of menu A", async () => {
    const date = localDateStr();
    localStorageMock.setItem(
      `order_${date}`,
      JSON.stringify({
        status: "draft",
        breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
        lunch: { Škôlka: { menuCounts: { A: 2 }, diets: { "Bez lepku": 1 } } },
        olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      }),
    );
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: false, lunch: true, olovrant: false }),
    );

    // Názov diéty musí byť z konštanty DIETS — inak ho `enforceStructure`
    // pri načítaní objednávky zahodí a počet diét vyjde 0.
    (OrderService.getAvailableDiets as Mock).mockReturnValue(["Bez lepku"]);
    (OrderService.getAvailableDietsWithSpecial as Mock).mockReturnValue(["Bez lepku"]);

    renderPage();

    const lunchCard = getMealCard("Obed");
    const skolkaRow = getCategoryRow(lunchCard, "Škôlka");
    fireEvent.click(await within(skolkaRow).findByRole("button", { name: /Diéty/ }));

    const dietInput = await screen.findByLabelText("Počet diéty Bez lepku");
    // Diéty už nemajú strop — napísaná 5 sa uloží a pripočíta sa k bežným porciám.
    fireEvent.change(dietInput, { target: { value: "5" } });
    fireEvent.blur(dietInput);

    await waitFor(() => {
      expect(getOrderData(date).lunch["Škôlka"].diets["Bez lepku"]).toBe(5);
    });
    // Pôvodne A=2 s 1 diétou => 1 bežná porcia; po zmene 1 + 5 = 6.
    expect(getOrderData(date).lunch["Škôlka"].menuCounts.A).toBe(6);
  });

  it("shows the plain menu A count with diets broken out into their own row", async () => {
    const date = localDateStr();
    // Stará objednávka: A=10 znamenalo „7 bežných + 3 diétne“.
    localStorageMock.setItem(
      `order_${date}`,
      JSON.stringify({
        status: "draft",
        breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
        lunch: { Škôlka: { menuCounts: { A: 10 }, diets: { "Bez lepku": 3 } } },
        olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      }),
    );
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: false, lunch: true, olovrant: false }),
    );
    (OrderService.getAvailableDiets as Mock).mockReturnValue(["Bez lepku"]);
    (OrderService.getAvailableDietsWithSpecial as Mock).mockReturnValue(["Bez lepku"]);

    renderPage();

    const lunchCard = getMealCard("Obed");
    const skolkaRow = getCategoryRow(lunchCard, "Škôlka");

    const menuAInput = await within(skolkaRow).findByLabelText(
      "Počet porcií pre menu A",
    );
    expect((menuAInput as HTMLInputElement).value).toBe("7");

    const dietButton = within(skolkaRow).getByRole("button", { name: /Diéty/ });
    expect(dietButton).toHaveTextContent("3");
  });

  it("hides breakfast and olovrant menu choices configured to only menu A", async () => {
    mockPrevadzkaWithPerMealMenus();
    const date = localDateStr();
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: true, lunch: true, olovrant: true }),
    );

    renderPage();

    // „Škôlka“ má v GROUP_CONFIG len menu A, takže rozdiel medzi chodmi vidno
    // len na kategórii, ktorá menu B vôbec ponúka.
    const row = (meal: string) => getCategoryRow(getMealCard(meal), "ZŠ 1.stupeň");

    await waitFor(() => {
      expect(within(row("Obed")).getByText("Menu B")).toBeInTheDocument();
    });
    expect(within(row("Raňajky")).queryByText("Menu B")).not.toBeInTheDocument();
    expect(within(row("Olovrant")).queryByText("Menu B")).not.toBeInTheDocument();
  });

  it("offers Menu B for Škôlka when the prevádzka has it in visible_menus (kategória menu sama neobmedzuje)", async () => {
    mockPrevadzkaWithPerMealMenus();
    const date = localDateStr();
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: false, lunch: true, olovrant: false }),
    );

    renderPage();

    const lunchCard = getMealCard("Obed");
    const skolkaRow = getCategoryRow(lunchCard, "Škôlka");

    await waitFor(() => {
      expect(within(skolkaRow).getByText("Menu B")).toBeInTheDocument();
    });
  });

  it("Copy Breakfast: Copies from Previous Day Lunch", async () => {
    const today = localDateStr();
    const prevDay = new Date();
    prevDay.setDate(prevDay.getDate() - 1);
    const yesterdayStr = localDateStr(prevDay);

    // 1. Seed YESTERDAY's order
    const prevOrder = {
      status: "submitted",
      breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      lunch: { Škôlka: { menuCounts: { A: 5 }, diets: {} } },
      olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
    };
    localStorageMock.setItem(
      `order_${yesterdayStr}`,
      JSON.stringify(prevOrder),
    );

    // 2. Seed TODAY's order
    const todayOrder = {
      status: "draft",
      breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      lunch: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
    };
    localStorageMock.setItem(`order_${today}`, JSON.stringify(todayOrder));
    localStorageMock.setItem(
      `activeMeals_${today}`,
      JSON.stringify({ breakfast: true, lunch: true, olovrant: false }),
    );

    renderPage();

    // 3. Locate Breakfast Card
    const breakfastTitle = screen.getAllByText("Raňajky")[0];
    const breakfastCard = breakfastTitle.closest(".zp-meal");
    expect(breakfastCard).toBeInTheDocument();

    // 4. Find "Načítať z včera" button
    const copyBtn = await within(breakfastCard as HTMLElement).findByText(
      /Načítať z včerajška/i,
    );
    expect(copyBtn).toBeInTheDocument();

    // 5. Activate
    fireEvent.click(copyBtn);

    // 6. Verify Data Transfer
    await waitFor(() => {
      const updated = getOrderData(today);
      expect(updated.breakfast["Škôlka"].menuCounts["A"]).toBe(5);
    });
  });
  it("renders the order page with meals", () => {
    renderPage();
    expect(screen.getAllByText("Raňajky")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Obed")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Olovrant")[0]).toBeInTheDocument();
  });

  it("blocks ordering a main_course menu variant the jedálniček didn't publish for that day", async () => {
    // The meal-plan-availability fetch only runs when `user` is set; the
    // default mock omits it, so give this test a real user.
    (useAuth as Mock).mockReturnValue({
      logout: vi.fn(),
      apiFetch: mockApiFetch,
      user: { id: 1, email: "client@example.com" },
    });

    // Only Menu A was published for main_course that day (legacy-style
    // per-variant selection). The jedálniček category (main_course) must
    // correctly map onto the order form's "lunch" meal so Menu B/C/V get
    // marked as unavailable/occupied.
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(
          makeMockResponse({
            deadline_breakfast: "10:00",
            deadline_breakfast_is_day_before: false,
            deadline_lunch: "10:00",
            deadline_lunch_is_day_before: false,
            deadline_olovrant: "10:00",
            deadline_olovrant_is_day_before: false,
          }),
        );
      }
      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({ id: 1, status: "draft", data: {} }),
        );
      }
      if (url.includes("/meal-plans/by-date/")) {
        return Promise.resolve(
          makeMockResponse({
            exists: true,
            items: [
              { category: "main_course", menu_variant: "A", template_detail: {} },
            ],
          }),
        );
      }
      return Promise.resolve(makeMockResponse([]));
    });

    renderPage();

    // mealPlanAvailability starts as null (= unoccupied by default), so wait
    // for the request and flush the resulting setState/re-render before
    // asserting, rather than asserting on the pre-fetch render.
    await waitFor(() => {
      expect(
        mockApiFetch.mock.calls.some((call: unknown[]) =>
          (call[0] as string).includes("/meal-plans/by-date/"),
        ),
      ).toBe(true);
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getAllByText("zasednutá").length).toBeGreaterThan(0);
  });

  it("keeps meal-plan availability from the latest selected date when an earlier request resolves last", async () => {
    type DeferredResponse = {
      promise: Promise<ReturnType<typeof makeMockResponse>>;
      resolve: (response: ReturnType<typeof makeMockResponse>) => void;
      signal?: AbortSignal;
    };
    const mealPlanRequests: DeferredResponse[] = [];
    const original = mockApiFetch.getMockImplementation()!;

    // useAuth's default mock factory (`vi.fn(() => ({...}))`) returns a fresh
    // `user` object on every call, which the fetch effects depend on — that
    // makes them refire on every render instead of only on real date/user
    // changes. Pin a stable reference for this test so the assertions below
    // observe only the deliberate "Ďalší deň" click, not mock-driven churn.
    (useAuth as Mock).mockReturnValue({
      logout: vi.fn(),
      apiFetch: mockApiFetch,
      user: { id: 1, email: "client@example.com" },
    });

    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/meal-plans/by-date/")) {
        let resolve!: DeferredResponse["resolve"];
        const promise = new Promise<ReturnType<typeof makeMockResponse>>((promiseResolve) => {
          resolve = promiseResolve;
        });
        mealPlanRequests.push({ promise, resolve, signal: init?.signal ?? undefined });
        return promise;
      }
      return original(url, init);
    });

    renderPage(true);

    await waitFor(() => expect(mealPlanRequests).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Ďalší deň" }));
    await waitFor(() => expect(mealPlanRequests).toHaveLength(2));
    expect(mealPlanRequests[0].signal?.aborted).toBe(true);

    await act(async () => {
      mealPlanRequests[1].resolve(makeMockResponse({
        exists: true,
        items: [
          { category: "main_course", menu_variant: "A", template_detail: {} },
        ],
      }));
      await mealPlanRequests[1].promise;
    });
    await waitFor(() => {
      expect(screen.getByTestId("meal-plan-availability")).toHaveTextContent('{"lunch":["A"]}');
    });

    await act(async () => {
      mealPlanRequests[0].resolve(makeMockResponse({ exists: false, items: [] }));
      await mealPlanRequests[0].promise;
    });
    expect(screen.getByTestId("meal-plan-availability")).toHaveTextContent('{"lunch":["A"]}');
  });

  it("does not mark any menu as occupied when the jedálniček uses variant-less catalog selections", async () => {
    (useAuth as Mock).mockReturnValue({
      logout: vi.fn(),
      apiFetch: mockApiFetch,
      user: { id: 1, email: "client@example.com" },
    });

    // A variant-less plan item is a single uniform selection for the whole day.
    // This must NOT be treated as "no menu variants available" (which would
    // grey out every 'Menu A/B/...' option on the order form).
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(
          makeMockResponse({
            deadline_breakfast: "10:00",
            deadline_breakfast_is_day_before: false,
            deadline_lunch: "10:00",
            deadline_lunch_is_day_before: false,
            deadline_olovrant: "10:00",
            deadline_olovrant_is_day_before: false,
          }),
        );
      }
      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({ id: 1, status: "draft", data: {} }),
        );
      }
      if (url.includes("/meal-plans/by-date/")) {
        return Promise.resolve(
          makeMockResponse({
            exists: true,
            items: [
              { category: "breakfast_snack", menu_variant: "", template_detail: {} },
              { category: "soup", menu_variant: "", template_detail: {} },
              { category: "main_course", menu_variant: "", template_detail: {} },
              { category: "afternoon_snack", menu_variant: "", template_detail: {} },
            ],
          }),
        );
      }
      return Promise.resolve(makeMockResponse([]));
    });

    renderPage();

    await waitFor(() => {
      expect(
        mockApiFetch.mock.calls.some((call: unknown[]) =>
          (call[0] as string).includes("/meal-plans/by-date/"),
        ),
      ).toBe(true);
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.queryByText("zasednutá")).not.toBeInTheDocument();
  });

  it('displays "Termín uplynul" badge when deadline passed', () => {
    (OrderService.checkDeadline as Mock).mockImplementation(
      (_date: string, meal: string) => {
        if (meal === "breakfast") return false;
        return true;
      },
    );

    renderPage();
    const badges = screen.getAllByText(/Termín uplynul/);
    expect(badges.length).toBeGreaterThan(0);
  });

  it("Celodenná: is closed when the first visible meal deadline has passed", () => {
    (OrderService.checkDeadline as Mock).mockImplementation(
      (_date: string, meal: string) => meal !== "breakfast",
    );

    renderPage();

    expect(
      screen.getByText("Termín prvého jedla uplynul · Celodenná objednávka je uzavretá"),
    ).toBeVisible();

    const fullDaySwitch = screen.getByRole("switch", {
      name: /Celodenná objednávka/i,
    });
    fireEvent.click(fullDaySwitch);

    expect(
      screen.queryByText("Celodenná objednávka je aktívna"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Odoslať objednávku").closest("button")).not.toBeDisabled();
  });

  it("Submit button is disabled when ALL deadlines passed", () => {
    (OrderService.checkDeadline as Mock).mockReturnValue(false);
    renderPage();
    const submitBtn = screen.getByText("Odoslať objednávku").closest("button");
    expect(submitBtn).toBeDisabled();
    expect(
      screen.getByText(
        "Na tento deň už nie je možné vytvoriť objednávku (termín uplynul).",
      ),
    ).toBeVisible();
  });

  it("Submit button is enabled with 0 portions (zero order = Bez objednávky)", () => {
    // Deadline not passed, but 0 portions → still enabled (intentional empty/null order)
    (OrderService.checkDeadline as Mock).mockReturnValue(true);
    renderPage();
    const submitBtn = screen.getByText("Odoslať objednávku").closest("button");
    expect(submitBtn).not.toBeDisabled();
    // Deadline msg not present
    expect(
      screen.queryByText(
        "Na tento deň už nie je možné vytvoriť objednávku (termín uplynul).",
      ),
    ).not.toBeInTheDocument();
  });

  it("shows the server's specific reason (which meal, which deadline) when submit fails after deadline", async () => {
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(
          makeMockResponse({
            deadline_breakfast: "10:00",
            deadline_breakfast_is_day_before: false,
            deadline_lunch: "10:00",
            deadline_lunch_is_day_before: false,
            deadline_olovrant: "10:00",
            deadline_olovrant_is_day_before: false,
          }),
        );
      }

      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({ id: 1, status: "draft", data: {} }),
        );
      }

      if (url.includes("/orders/") && init?.method === "POST") {
        return Promise.resolve(
          makeMockResponse(
            {
              error: {
                code: "order_deadline_passed",
                message: "Objednávku pre obed už nie je možné meniť. Termín: 13.03.2026 10:00",
                details: {
                  deadline: "13.03.2026 10:00",
                  current_time: "13.03.2026 10:01",
                },
              },
            },
            false,
          ),
        );
      }

      return Promise.resolve(makeMockResponse([]));
    });

    renderPage();

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    // Predtým appka toto zahodila a ukázala len všeobecnú hlášku — klient
    // tak nemal ako zistiť, KTORÉ jedlo mu blokuje aj zvyšok objednávky
    // (incident Vyšehradská, 2.9.2026). Server pošle presný dôvod, appka ho
    // teraz musí ukázať namiesto prekrytia všeobecným textom.
    expect(
      await screen.findByText(
        "Objednávku pre obed už nie je možné meniť. Termín: 13.03.2026 10:00",
      ),
    ).toBeInTheDocument();
  });

  // ── URL dátum → selectedDate (Emjoy, 3.9.2026) ──────────────────────────────
  // `selectedDate` žije v AppProvider (jedna inštancia pre celú appku, prežíva
  // navigáciu medzi stránkami) a `useOrder` ho defaultne inicializuje na
  // "dnes" — bez ohľadu na to, na akom dátume URL reálne je. Tieto testy
  // chránia LOGIKU synchronizácie (URL dátum sa naozaj uplatní; neskoršia
  // legitímna zmena cez DaySelector sa naspäť neprepíše) — samotný race
  // (efekt bežiaci PO vykreslení vs. klik v tom okne) sa v jsdom/RTL
  // nedá autenticky reprodukovať, lebo `act()` efekty flushuje synchrónne
  // skôr, než test stihne čokoľvek pozorovať medzi krokmi.

  it("submits the order under the date from the URL, not the hook's 'today' default", async () => {
    const today = localDateStr();
    const tomorrow = localDateStr(new Date(Date.now() + 24 * 60 * 60 * 1000));

    renderPage(false, [`/order?date=${tomorrow}`]);

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(postCall![1].body as string);
      expect(body.date).toBe(tomorrow);
      expect(body.date).not.toBe(today);
    });
  });

  it("does not re-apply a stale URL date after the user picks a different day via DaySelector", async () => {
    const today = localDateStr();
    // DaySelector's "Ďalší deň" calls `stepBusinessDay`, ktorý víkend
    // preskočí (napr. z piatka rovno na pondelok) — naivné "+1 deň" tu bolo
    // vždy zle mimo Po-Št a test tak padal, kedykoľvek bežal v piatok
    // (spadol by na sobotu, ktorú appka preskočí na pondelok). Rovnaká
    // funkcia ako v `DaySelector.tsx`, nech test sedí s appkou v ktorýkoľvek deň.
    const nextBusinessDay = stepBusinessDay(fromDateKey(today), 1);
    if (!nextBusinessDay) throw new Error("stepBusinessDay returned null");
    const tomorrow = toDateKey(nextBusinessDay);

    // URL zostáva na `today` počas celého testu — DaySelector mení
    // selectedDate priamo, bez navigácie (rovnaký mechanizmus ako v teste
    // "keeps meal-plan availability..." vyššie).
    renderPage(false, [`/order?date=${today}`]);

    fireEvent.click(screen.getByRole("button", { name: "Ďalší deň" }));

    await waitFor(() => {
      expect(
        mockApiFetch.mock.calls.some(
          (call) => call[0]?.includes(`/orders/by-date/${tomorrow}/`),
        ),
      ).toBe(true);
    });

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(postCall![1].body as string);
      // Submit musí ísť na deň, ktorý si user reálne vybral cez DaySelector
      // (zajtra) — nie sa vrátiť na pôvodný URL dátum (dnes).
      expect(body.date).toBe(tomorrow);
    });
  });

  // ── Celodenná objednávka (Full-day order) ───────────────────────────────────

  it("Celodenná: renders the full-day card alongside individual meal cards", () => {
    renderPage();
    expect(screen.getAllByText("Celodenná objednávka")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Raňajky")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Obed")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Olovrant")[0]).toBeInTheDocument();
  });

  it("Celodenná: toggling ON locks all individual meal cards with status message", async () => {
    renderPage();

    const fullDaySwitch = screen.getByRole("switch", {
      name: /Celodenná objednávka/i,
    });
    fireEvent.click(fullDaySwitch);

    await waitFor(() => {
      const lockBanners = screen.getAllByText("Celodenná objednávka je aktívna");
      // One banner per individual meal card (Raňajky, Obed, Olovrant) = 3
      expect(lockBanners.length).toBeGreaterThanOrEqual(3);
    });
  });

  it("Celodenná: submitting sends the same full-day data for all three meals", async () => {
    const date = localDateStr();

    // Seed full-day portion data. fullDayOrder itself cannot be pre-seeded via
    // localStorage because safeParse/enforceStructure returns the fallback for
    // primitive (boolean) values. We enable it through the UI toggle instead.
    localStorageMock.setItem(
      `fullDayData_${date}`,
      JSON.stringify({
        Škôlka: { menuCounts: { A: 7 }, diets: {} },
      }),
    );

    renderPage();

    // Enable full-day order via the toggle switch
    const fullDaySwitch = screen.getByRole("switch", {
      name: /Celodenná objednávka/i,
    });
    fireEvent.click(fullDaySwitch);

    // Wait until individual cards show the lock banner (confirms fullDayOrder is ON)
    await waitFor(() => {
      expect(
        screen.getAllByText("Celodenná objednávka je aktívna").length,
      ).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    // Verify the POST request has all 3 meals with full-day data
    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();

      const body = JSON.parse(postCall![1].body as string);

      // All three meals must carry the identical full-day portion data
      expect(body.data.breakfast["Škôlka"].menuCounts["A"]).toBe(7);
      expect(body.data.lunch["Škôlka"].menuCounts["A"]).toBe(7);
      expect(body.data.olovrant["Škôlka"].menuCounts["A"]).toBe(7);
      // A a server-persisted flag (not just localStorage) lets the next
      // load restore Celodenná on ANY device/browser — see the next test.
      expect(body.data.full_day_order).toBe(true);
    });
  });

  // ── Celodenná príznak musí prežiť aj bez localStorage (Veselý Úľ, 4.9.2026) ─
  //
  // Predtým `fullDayOrder` žil len vo frontend localStorage, per-browser.
  // Klient v móde "celý deň naraz" na jednom zariadení, na inom appka bez
  // varovania editovala jedlá nezávisle — časť dňa sa tak dala nechtiac
  // odoslať bez zvyšku (raňajky ostali na starom počte, keď sa obed aj
  // olovrant znížili). Server teraz vracia príznak ako súčasť `data`, takže
  // ho appka na ĽUBOVOĽNOM zariadení/prehliadači vie obnoviť.
  it("Celodenná: restores the toggle from the server on a fresh browser with no local draft", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(makeMockResponse({}));
      }
      if (url.includes("/orders/by-date/")) {
        return Promise.resolve(
          makeMockResponse({
            id: 1,
            status: "submitted",
            data: {
              full_day_order: true,
              breakfast: { Škôlka: { menuCounts: { A: 7 }, diets: {} } },
              lunch: { Škôlka: { menuCounts: { A: 7 }, diets: {} } },
              olovrant: { Škôlka: { menuCounts: { A: 7 }, diets: {} } },
            },
          }),
        );
      }
      return Promise.resolve(makeMockResponse([]));
    });

    // Zámerne nič v localStorage — presne "iné zariadenie/prehliadač", ktoré
    // Celodennú ešte nikdy lokálne nezapínalo.
    renderPage();

    await waitFor(() => {
      expect(
        screen.getAllByText("Celodenná objednávka je aktívna").length,
      ).toBeGreaterThanOrEqual(1);
    });

    // Ďalší submit musí ísť s celodennými dátami za všetky 3 jedlá — nesmie
    // potichu spadnúť späť do per-jedlového módu.
    fireEvent.click(screen.getByText("Odoslať objednávku"));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(postCall![1].body as string);
      expect(body.data.full_day_order).toBe(true);
      expect(body.data.breakfast["Škôlka"].menuCounts["A"]).toBe(7);
      expect(body.data.lunch["Škôlka"].menuCounts["A"]).toBe(7);
      expect(body.data.olovrant["Škôlka"].menuCounts["A"]).toBe(7);
    });
  });

  it("Celodenná: submitting with fullDayOrder OFF sends per-meal data independently", async () => {
    const date = localDateStr();

    // Full-day order is NOT active; each meal has its own data
    localStorageMock.setItem(
      `order_${date}`,
      JSON.stringify({
        status: "draft",
        breakfast: { Škôlka: { menuCounts: { A: 2 }, diets: {} } },
        lunch: { Škôlka: { menuCounts: { A: 5 }, diets: {} } },
        olovrant: { Škôlka: { menuCounts: { A: 1 }, diets: {} } },
      }),
    );
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: true, lunch: true, olovrant: true }),
    );

    renderPage();

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();

      const body = JSON.parse(postCall![1].body as string);

      // Each meal must have its own distinct count — NOT the same value
      expect(body.data.breakfast["Škôlka"].menuCounts["A"]).toBe(2);
      expect(body.data.lunch["Škôlka"].menuCounts["A"]).toBe(5);
      expect(body.data.olovrant["Škôlka"].menuCounts["A"]).toBe(1);
    });
  });

  // ── Submit nesmie prepísať nedotknuté jedlo starým draftom (Emjoy, 3.9.2026) ─
  //
  // Škola upravila len raňajky; appka poslala CELÚ objednávku (backend robí
  // `instance.data = new_data`, žiadny merge) vrátane obeda, ktorého lokálny
  // stav bol ešte starý localStorage draft z inej session — s Menu B/C = 0,
  // hoci server mal reálne objednané B=1, C=2. Submit tak potichu vynuloval
  // objednané Menu B/C na jedle, ktorého sa klient v danej session vôbec
  // nedotkol. Fix: submit počká na počiatočný GET pre (dátum, prevádzka) a
  // pre nedotknuté jedlá uprednostní čerstvú serverovú hodnotu pred lokálnym
  // draftom; dotknuté jedlá (klient ich v tejto session reálne menil) idú
  // tak, ako sú.
  it("waits for the server order and uses it for an untouched meal, not a stale local draft", async () => {
    const date = localDateStr();

    // Starý localStorage draft: obed má Dospelý (SŠ) Menu B/C už na nule.
    localStorageMock.setItem(
      `order_${date}`,
      JSON.stringify({
        status: "submitted",
        breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
        lunch: {
          Škôlka: { menuCounts: { A: 23 }, diets: {} },
          "Dospelý (SŠ)": { menuCounts: { A: 0, B: 0, C: 0 }, diets: {} },
        },
        olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
      }),
    );
    localStorageMock.setItem(
      `activeMeals_${date}`,
      JSON.stringify({ breakfast: true, lunch: true, olovrant: false }),
    );

    let resolveOrderFetch!: (value: unknown) => void;
    const pendingOrderFetch = new Promise((resolve) => {
      resolveOrderFetch = resolve;
    });

    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/admin/global-settings/")) {
        return Promise.resolve(makeMockResponse({}));
      }
      if (url.includes("/orders/by-date/")) {
        // Server GET visí — ešte neodpovedal, presne ako pri pomalej sieti.
        return pendingOrderFetch as Promise<Response>;
      }
      if (url.includes("/orders/") && init?.method === "POST") {
        return Promise.resolve(makeMockResponse({}));
      }
      return Promise.resolve(makeMockResponse([]));
    });

    renderPage();

    // Klient upraví LEN raňajky — obed (a jeho Dospelý B/C) nechá netknutý.
    const breakfastCard = getMealCard("Raňajky");
    const skolkaRow = getCategoryRow(breakfastCard, "Škôlka");
    const input = await within(skolkaRow).findByLabelText(
      "Počet porcií pre menu A",
    );
    fireEvent.change(input, { target: { value: "23" } });
    fireEvent.blur(input);

    await waitFor(() => {
      expect(getOrderData(date).breakfast["Škôlka"].menuCounts.A).toBe(23);
    });

    fireEvent.click(screen.getByText("Odoslať objednávku"));

    // GET ešte visí — submit nesmie odísť so starým draftom skôr, než príde
    // odpoveď servera.
    expect(
      mockApiFetch.mock.calls.some((call) => call[1]?.method === "POST"),
    ).toBe(false);

    // Server odpovie: obed má v skutočnosti Dospelý (SŠ) B=1, C=2.
    await act(async () => {
      resolveOrderFetch(
        makeMockResponse({
          id: 1793,
          status: "submitted",
          data: {
            breakfast: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
            lunch: {
              Škôlka: { menuCounts: { A: 23 }, diets: {} },
              "Dospelý (SŠ)": {
                menuCounts: { A: 0, B: 1, C: 2 },
                diets: {},
              },
            },
            olovrant: { Škôlka: { menuCounts: { A: 0 }, diets: {} } },
          },
        }),
      );
    });

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        (call) => call[0]?.includes("/orders/") && call[1]?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(postCall![1].body as string);
      // Raňajky boli v tejto session reálne upravené — ide lokálna hodnota.
      expect(body.data.breakfast["Škôlka"].menuCounts.A).toBe(23);
      // Obed sa nedotkol — musí ísť čerstvá serverová hodnota, nie 0 zo
      // starého draftu.
      expect(body.data.lunch["Dospelý (SŠ)"].menuCounts.B).toBe(1);
      expect(body.data.lunch["Dospelý (SŠ)"].menuCounts.C).toBe(2);
    });
  });
});
