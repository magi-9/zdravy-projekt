import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminDashboard from "./AdminDashboard";

const mockApiFetch = vi.fn();
const mockToastError = vi.fn();
const mockToastSuccess = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

vi.mock("../../context/ToastContext", () => ({
  useToast: () => ({
    error: mockToastError,
    success: mockToastSuccess,
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

const makeMockResponse = (payload: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 400,
  json: () => Promise.resolve(payload),
  blob: () => Promise.resolve(new Blob()),
  text: () => Promise.resolve(JSON.stringify(payload)),
  clone() {
    return makeMockResponse(payload, ok);
  },
});

// "Nastavenia tabuľky" sa pamätajú v localStorage (2.9.2026) — globálny hook,
// nech medzi sebou nepresiaknu ani testy v iných `describe` blokoch nižšie.
beforeEach(() => {
  localStorage.clear();
});

const mockDashboardRequests = (
  gramage: unknown,
  orderReport?: unknown,
  isClosed = false,
) => {
  mockApiFetch.mockImplementation((url: string) => {
    if (url.includes("/admin/closed-days/")) {
      return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: isClosed }));
    }
    if (url.includes("/admin/meal-plans/gramage-dashboard/")) {
      return Promise.resolve(makeMockResponse(gramage));
    }
    if (url.includes("/admin/meal-plans/gramage-dashboard-pdf/")) {
      return Promise.resolve(makeMockResponse(new Blob()));
    }
    if (url.includes("/admin/summary/daily-report/") && orderReport) {
      return Promise.resolve(makeMockResponse(orderReport));
    }
    throw new Error(`Unexpected URL ${url}`);
  });
};

it("shows the API error when the gramage table cannot be loaded", async () => {
  mockApiFetch.mockImplementation((url: string) => {
    if (url.includes("/admin/closed-days/")) {
      return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: false }));
    }
    if (url.includes("/admin/meal-plans/gramage-dashboard/")) {
      return Promise.resolve(makeMockResponse(
        { error: { message: "Šablóna ‚Hlavný chod + vajce‘ má neplatnú gramáž." } },
        false,
      ));
    }
    throw new Error(`Unexpected URL ${url}`);
  });

  render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

  expect(await screen.findByText("Šablóna ‚Hlavný chod + vajce‘ má neplatnú gramáž.")).toBeInTheDocument();
});

// "Nastavenia tabuľky" je v DOM (teda nájditeľné cez `findByRole`) hneď od
// prvého renderu, ale ostáva `disabled`, kým sa dáta nenačítajú (`hasData`) —
// klik naň skôr je no-op a modal sa nikdy neotvorí. Lokálne to prejde skoro
// vždy (mikrotask s dátami stihne doraziť), v CI je to flaky (#565).
const openTableSettings = async () => {
  const button = await screen.findByRole("button", { name: /nastavenia tabuľky/i });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
};

// Tabuľku renderuje hotový `spec` z backendu (gramage_table_spec.py) — fixture
// ho musí niesť tiež, inak testuje niečo, čo v aplikácii nikdy nenastane.
const emptySpec = (columns = 0) => ({
  total_columns: 1 + columns,
  sections: [],
  header: { corner: "Prevádzka / Riadok", groups: [], components: [] },
  rows: [],
  footer: [],
});

const EMPTY_GRAMAGE = {
  date: "2026-07-03",
  meal_plan_id: null,
  col_groups: [],
  rows: [],
  totals: [],
  count_summary: [],
  spec: emptySpec(),
};

const ORDER_REPORT = {
  date: "2026-07-03",
  rows: [
    {
      user_id: 1,
      name: "Skolka Krasnanko",
      email: "krasnanko@edupage.local",
      breakfast: {
        categories: [
          {
            name: "Škôlka",
            menus: { A: 12 },
            diets: { Bezlepkova: 2 },
            total: 12,
          },
        ],
        total: 14,
      },
      lunch: {
        categories: [
          {
            name: "Škôlka",
            menus: { A: 20, B: 5 },
            diets: {},
            total: 25,
          },
        ],
        total: 25,
      },
      olovrant: {
        categories: [],
        total: 0,
      },
      total: 39,
    },
  ],
  totals: {
    breakfast: { menus: { A: 12 }, diets: { Bezlepkova: 2 }, total: 14 },
    lunch: { menus: { A: 20, B: 5 }, diets: {}, total: 25 },
    olovrant: { menus: {}, diets: {}, total: 0 },
    grand: 39,
  },
};

const ORDER_REPORT_WITH_BOTH_SHAPES = {
  ...ORDER_REPORT,
  rows: [
    {
      ...ORDER_REPORT.rows[0],
      breakfast: {
        menus: { A: 99 },
        diets: { StaryTvar: 99 },
        categories: [
          {
            name: "Škôlka",
            menus: { A: 12 },
            diets: { Bezlepkova: 2 },
            total: 12,
          },
        ],
        total: 14,
      },
    },
  ],
};

const GRAMAGE_WITH_PLAN = {
  date: "2026-07-06",
  meal_plan_id: 7,
  col_groups: [
    {
      key: "main_course_B",
      label: "Hlavný chod Menu B",
      meal: "main_course",
      variant: "B",
      template_name: "Hlavny chod 1",
      components: [{ label: "jedlo", base_grams: "100", unit: "g" }],
    },
  ],
  rows: [],
  totals: [["0.00"]],
  count_summary: [],
  spec: {
    ...emptySpec(1),
    header: {
      corner: "Prevádzka / Riadok",
      groups: [{ text: "Menu B", sub: "Hlavny chod 1", css: "grp mh-menuB-1", colspan: 1 }],
      components: [{ text: "jedlo", sub: "100g", css: "comp mh-menuB-2" }],
    },
  },
};

describe("AdminDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:report") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });

  it("shows order counts when the selected date has orders but no meal plan", async () => {
    mockDashboardRequests(EMPTY_GRAMAGE, ORDER_REPORT);

    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    expect(await screen.findByText("Počty objednávok bez gramáže")).toBeInTheDocument();
    expect(screen.getByText("Skolka Krasnanko")).toBeInTheDocument();
    expect(screen.getByText("A: 12")).toBeInTheDocument();
    expect(screen.getByText("Bezlepkova: 2")).toBeInTheDocument();
    expect(screen.getByText("A: 20, B: 5")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/admin/summary/daily-report/"),
      );
    });
  });

  it("does not fetch the order-count fallback when gramaz data has a meal plan", async () => {
    mockDashboardRequests(GRAMAGE_WITH_PLAN);

    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    expect(await screen.findAllByText("Menu B")).not.toHaveLength(0);
    expect(screen.queryByText("Hlavný chod Menu B")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });
    expect(mockApiFetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/admin/summary/daily-report/"),
    );
  });

  it("prefers category counts over top-level fallback counts", async () => {
    mockDashboardRequests(EMPTY_GRAMAGE, ORDER_REPORT_WITH_BOTH_SHAPES);

    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    expect(await screen.findByText("Počty objednávok bez gramáže")).toBeInTheDocument();
    expect(screen.getByText("A: 12")).toBeInTheDocument();
    expect(screen.getByText("Bezlepkova: 2")).toBeInTheDocument();
    expect(screen.queryByText("A: 99")).not.toBeInTheDocument();
    expect(screen.queryByText("StaryTvar: 99")).not.toBeInTheDocument();
  });

  it("shows Uzamknúť for an open date and closes it after confirmation", async () => {
    let closed = false;
    mockApiFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/admin/meal-plans/gramage-dashboard/")) {
        return Promise.resolve(makeMockResponse(EMPTY_GRAMAGE));
      }
      if (url.includes("/admin/summary/daily-report/")) {
        return Promise.resolve(makeMockResponse(ORDER_REPORT));
      }
      if (url.includes("/admin/closed-days/") && options?.method === "POST") {
        closed = true;
        return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: true }));
      }
      if (url.includes("/admin/closed-days/")) {
        return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: closed }));
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const lockButton = await screen.findByRole("button", { name: /uzamknúť/i });
    fireEvent.click(lockButton);
    const dialog = screen.getByRole("dialog", { name: /uzamknúť objednávky/i });
    fireEvent.click(within(dialog).getByRole("button", { name: "Uzamknúť" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/admin/closed-days/"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"date"'),
        }),
      );
      expect(screen.getByRole("status")).toHaveTextContent("Deň je uzavretý");
    });
    expect(screen.getByRole("button", { name: /^pdf$/i })).toBeInTheDocument();
    expect(mockToastSuccess).toHaveBeenCalledWith("Deň bol uzavretý.");
  });

  it("unlocks a closed date after explicit confirmation and returns to the open state", async () => {
    mockApiFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/admin/meal-plans/gramage-dashboard/")) {
        return Promise.resolve(makeMockResponse(GRAMAGE_WITH_PLAN));
      }
      if (url.includes("/admin/closed-days/unlock/") && options?.method === "DELETE") {
        return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: false }));
      }
      if (url.includes("/admin/closed-days/")) {
        return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: true }));
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const unlockButton = await screen.findByRole("button", { name: /odomknúť/i });
    fireEvent.click(unlockButton);
    const dialog = screen.getByRole("dialog", { name: /odomknúť objednávky/i });
    expect(within(dialog).getByText(/znova otvorí na úpravy objednávok, diét/i)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Odomknúť" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/admin/closed-days/unlock/"),
        expect.objectContaining({
          method: "DELETE",
          body: expect.stringContaining('"date"'),
        }),
      );
      expect(screen.getByRole("button", { name: /uzamknúť/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(mockToastSuccess).toHaveBeenCalledWith("Deň bol odomknutý.");
  });
});

// ── Tabuľka sa renderuje z hotového spec-u ───────────────────────────────────
// Rovnaký spec vykresľuje aj PDF (gramage_table_html.py), takže tieto testy
// zamykajú, že React zo spec-u nič nedomýšľa ani nevynecháva.

const cell = (text: string, css = "") => ({ text, css });

const GRAMAGE_WITH_ROWS = {
  ...EMPTY_GRAMAGE,
  // Tabuľka s riadkami vzniká len z platného jedálneho lístka. Bez ID by
  // dashboard správne prepol na fallback denného reportu, čo táto fixture
  // netestuje a pri refetchi nechávalo neobslúžený request.
  meal_plan_id: 1,
  col_groups: [{ key: "menuA" }],
  spec: {
    total_columns: 2,
    sections: [
      { key: "soup", label: "Polievka", selected: true },
      { key: "main_course_A", label: "Menu A", selected: true },
      { key: "afternoon_snack", label: "Olovrant", selected: true },
    ],
    header: {
      corner: "Prevádzka / Riadok",
      groups: [{ text: "Menu A", sub: "Kuracie", css: "grp mh-menuA-1", colspan: 1 }],
      components: [{ text: "Mäso", sub: "300g", css: "comp mh-menuA-2" }],
    },
    rows: [
      {
        kind: "client",
        css: "client-row",
        group_id: "k1",
        cells: [
          {
            text: "MŠ Testovacia",
            meta: "štandard 8, diéty 2",
            meta_right: "spolu porcií 10",
            colspan: 2,
          },
        ],
      },
      {
        kind: "sub-row",
        css: "sub-row",
        group_id: "k1",
        collapsible: true,
        cells: [
          { text: "Škôlka - Obed Menu A", css: "lbl", count: "8" },
          cell("2400", "cell-num mh-menuA-cell"),
        ],
      },
      {
        kind: "summary-diet",
        css: "summ-diet",
        group_id: "k1",
        collapsible: true,
        color: "#966107",
        cells: [
          { text: "No Milk", css: "lbl", count: "2" },
          cell("600,5", "cell-num mh-menuA-cell"),
        ],
      },
    ],
    footer: [
      {
        kind: "total",
        css: "total",
        cells: [cell("CELKOM (g / ml)", "corner"), cell("3000,5")],
      },
    ],
  },
};

describe("GramageTable renders straight from the spec", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the header and footer but keeps client detail collapsed", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    expect(await screen.findByText("MŠ Testovacia")).toBeInTheDocument();
    // "Menu A" je aj chip filtra, preto hľadaj hlavičku vnútri tabuľky.
    const table = document.querySelector("table.zpa-gram")!;
    expect(within(table as HTMLElement).getByText("Menu A")).toBeInTheDocument();
    expect(screen.getByText("300g")).toBeInTheDocument();
    // Desatiny musia byť vidno — kuchyňa ich potrebuje.
    expect(screen.getByText("3000,5")).toBeInTheDocument();

    // Podriadky sú zbalené, kým klienta nerozklikneš.
    expect(screen.queryByText("Škôlka - Obed Menu A")).not.toBeInTheDocument();
  });

  it("shows the prevádzka note right after the client name even while collapsed (#513)", async () => {
    const withNote = {
      ...GRAMAGE_WITH_ROWS,
      spec: {
        ...GRAMAGE_WITH_ROWS.spec,
        rows: [
          {
            ...GRAMAGE_WITH_ROWS.spec.rows[0],
            cells: [
              { ...GRAMAGE_WITH_ROWS.spec.rows[0].cells[0], note: "bez cibule" },
            ],
          },
          ...GRAMAGE_WITH_ROWS.spec.rows.slice(1),
        ],
      },
    };
    mockDashboardRequests(withNote);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    // Vidno hneď, bez rozbalenia klienta.
    expect(await screen.findByText("bez cibule")).toBeInTheDocument();
  });

  it("reveals the sub-rows with their spec classes and colour on expand", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /MŠ Testovacia/ }));

    const subRow = screen.getByText("Škôlka - Obed Menu A").closest("tr");
    expect(subRow).toHaveClass("sub-row");
    expect(screen.getByText("2400")).toHaveClass("cell-num", "mh-menuA-cell");

    // Diéta sa odlišuje farbou písma, nie výplňou riadku.
    const dietRow = screen.getByText("No Milk").closest("tr");
    expect(dietRow).toHaveClass("summ-diet");
    expect(dietRow).toHaveStyle({ color: "#966107" });
  });

  it("renders the count as a badge, not as its own column", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /MŠ Testovacia/ }));

    const subRow = screen.getByText("Škôlka - Obed Menu A").closest("tr")!;
    expect(within(subRow).getByText("8")).toHaveClass("count-badge");
    expect(subRow.querySelectorAll("td")).toHaveLength(2);
  });
});

// ── Vyhľadávanie a poznámka prevádzky priamo z tabuľky (#573) ───────────────

const GRAMAGE_TWO_CLIENTS = {
  ...GRAMAGE_WITH_ROWS,
  // Top-level `rows` (nie `spec.rows`) nesie `client`/`prevadzka_id` — z neho
  // si search hľadá zhodu (rovnaký zdroj ako editácia poznámky, #573).
  rows: [
    { prevadzka_id: 1, client: "MŠ Testovacia" },
    { prevadzka_id: 2, client: "MŠ Iná" },
  ],
  spec: {
    ...GRAMAGE_WITH_ROWS.spec,
    rows: GRAMAGE_WITH_ROWS.spec.rows.map((row, i) => (i === 0 ? { ...row, prevadzka_id: 1 } : row)).concat({
      kind: "client",
      css: "client-row",
      group_id: "k2",
      prevadzka_id: 2,
      cells: [{ text: "MŠ Iná", meta: "štandard 3", meta_right: "spolu porcií 3", colspan: 2 }],
    }),
  },
};

describe("Vyhľadávanie prevádzky v tabuľke (#573)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("nezobrazuje ani neskrýva žiadne riadky počas písania", async () => {
    mockDashboardRequests(GRAMAGE_TWO_CLIENTS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    expect(await screen.findByText("MŠ Testovacia")).toBeInTheDocument();
    expect(screen.getByText("MŠ Iná")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Hľadať prevádzku/), { target: { value: "iná" } });

    // Tabuľka sa nezmenšuje počas písania — obe prevádzky ostávajú vidno.
    expect(screen.getByText("MŠ Testovacia")).toBeInTheDocument();
    expect(screen.getByText("MŠ Iná")).toBeInTheDocument();
  });

  it("po Enteri odscrolluje na prvú zhodnú prevádzku (ignoruje diakritiku a veľkosť písmen)", async () => {
    mockDashboardRequests(GRAMAGE_TWO_CLIENTS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await screen.findByText("MŠ Testovacia");
    const input = screen.getByPlaceholderText(/Hľadať prevádzku/);
    fireEvent.change(input, { target: { value: "INA" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // `scrollIntoView` je na `Element.prototype`, zdieľaný všetkými riadkami —
    // overuje sa preto count + ktorý konkrétny riadok dostal zvýraznenie.
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(document.getElementById("prevadzka-row-2")).toHaveClass("zpa-row-highlight");
    // Nezhodná prevádzka zostáva v tabuľke a nescrolluje sa k nej.
    expect(document.getElementById("prevadzka-row-1")).not.toHaveClass("zpa-row-highlight");
  });

  it("prázdne alebo nezhodné hľadanie nič neodscrolluje", async () => {
    mockDashboardRequests(GRAMAGE_TWO_CLIENTS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    const input = await screen.findByPlaceholderText(/Hľadať prevádzku/);
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "neexistuje" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(document.getElementById("prevadzka-row-1")!.scrollIntoView).not.toHaveBeenCalled();
    expect(document.getElementById("prevadzka-row-2")!.scrollIntoView).not.toHaveBeenCalled();
  });
});

describe("Poznámka prevádzky priamo z tabuľky (#573)", () => {
  const GRAMAGE_WITH_NOTE = {
    ...GRAMAGE_WITH_ROWS,
    rows: [{ prevadzka_id: 1, admin_order_note: "Pôvodná poznámka" }],
    spec: {
      ...GRAMAGE_WITH_ROWS.spec,
      rows: [
        { ...GRAMAGE_WITH_ROWS.spec.rows[0], prevadzka_id: 1 },
        ...GRAMAGE_WITH_ROWS.spec.rows.slice(1),
      ],
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/admin/closed-days/")) {
        return Promise.resolve(makeMockResponse({ date: "2026-07-03", is_closed: false }));
      }
      if (url.includes("/admin/meal-plans/gramage-dashboard/")) {
        return Promise.resolve(makeMockResponse(GRAMAGE_WITH_NOTE));
      }
      if (url.includes("/admin/facility-prevadzky/1/")) {
        return Promise.resolve(makeMockResponse({}));
      }
      throw new Error(`Unexpected URL ${url}`);
    });
  });

  it("otvorí editor s existujúcou poznámkou a uloží zmenu cez PATCH", async () => {
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await screen.findByText("MŠ Testovacia");
    fireEvent.click(screen.getByRole("button", { name: "Upraviť poznámku pre MŠ Testovacia" }));

    const textarea = await screen.findByDisplayValue("Pôvodná poznámka");
    fireEvent.change(textarea, { target: { value: "Nová poznámka" } });
    fireEvent.click(screen.getByRole("button", { name: /uložiť/i }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/admin/facility-prevadzky/1/"),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ admin_order_note: "Nová poznámka" }),
        }),
      ),
    );
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Poznámka uložená."));
  });
});

describe("Filter sekcií", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("re-fetches with the ticked sections and passes them to the export", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();

    // Odklik jednej sekcie pošle zvyšné dve — nie prázdny (= všetko) filter.
    fireEvent.click(await screen.findByRole("button", { name: "Olovrant" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(
          /gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&section=soup&section=main_course_A$/,
        ),
      );
    });

    // PDF tlačidlo je počas refetchu (`loading`) disabled — bez čakania na
    // jeho znovu-povolenie je klik hneď po predošlom `waitFor` občas no-op
    // (React ešte nestihol vyrenderovať `loading: false`), čo v CI flakuje.
    const pdfButton = screen.getByRole("button", { name: /^pdf$/i });
    await waitFor(() => expect(pdfButton).toBeEnabled());
    fireEvent.click(pdfButton);
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(
          /gramage-dashboard-pdf\/\?date=[\d-]+&meal_type=lunch&section=soup&section=main_course_A$/,
        ),
      );
    });
  });

  it("prints a single dispatch point when one is picked", async () => {
    // Kuchyňa vydáva z dvoch bodov naraz a chce tabuľku jedného z nich.
    mockDashboardRequests({
      ...GRAMAGE_WITH_ROWS,
      spec: {
        ...GRAMAGE_WITH_ROWS.spec,
        vydaje: [
          { key: "A", name: "Cluster A", selected: true },
          { key: "B", name: "Cluster B", selected: true },
        ],
      },
    });
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    // "Cluster A" je aj checkbox v sekcii "Diéty v sumári klastra" — zúž na
    // sekciu výberu clustra samotného.
    const clusterSection = (await screen.findByText("Cluster")).parentElement!;
    // Oba clustre sú predvolene "zapnuté" (prázdny výber = všetko) — odklik
    // Cluster A necháva zapnutý len Cluster B.
    fireEvent.click(within(clusterSection).getByRole("button", { name: "Cluster A" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&vydaj=B$/),
      );
    });

    const pdfButton = screen.getByRole("button", { name: /^pdf$/i });
    await waitFor(() => expect(pdfButton).toBeEnabled());
    fireEvent.click(pdfButton);
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard-pdf\/\?date=[\d-]+&meal_type=lunch&vydaj=B$/),
      );
    });
  });

  it("drops the filter entirely once everything is ticked again", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    const olovrant = await screen.findByRole("button", { name: "Olovrant" });
    fireEvent.click(olovrant);
    await waitFor(() => expect(olovrant).toHaveAttribute("aria-pressed", "true"));

    // Fixture hlási všetky sekcie ako zapnuté, takže druhý klik ich má zapnúť
    // späť a filter úplne zahodiť — inak by v URL zostal zbytočný balast.
    fireEvent.click(olovrant);
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch$/),
      );
    });
  });
});

describe("Nastavenia tabuľky (2.9.2026)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("turning off 'Zobraziť prázdne' sends show_empty=0", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Zobraziť prázdne prevádzky" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&show_empty=0$/),
      );
    });
  });

  it("turning off 'Zobraziť sumáre klastrov' sends cluster_summary=0 and hides the diet-per-cluster section", async () => {
    mockDashboardRequests({
      ...GRAMAGE_WITH_ROWS,
      spec: {
        ...GRAMAGE_WITH_ROWS.spec,
        vydaje: [
          { key: "A", name: "Cluster A", selected: true },
          { key: "B", name: "Cluster B", selected: true },
        ],
      },
    });
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    expect(await screen.findByText("Diéty v sumári klastra")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Zobraziť sumáre klastrov" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&cluster_summary=0$/),
      );
    });
    expect(screen.queryByText("Diéty v sumári klastra")).not.toBeInTheDocument();
  });

  it("'Zobraziť všetko rozbalené' sends expanded=1 a skutočne rozbalí každého klienta bez klikania", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await screen.findByText("MŠ Testovacia");
    // Predvolene zbalené — sub-riadok nie je vidno, kým naň admin neklikne.
    expect(screen.queryByText("Škôlka - Obed Menu A")).not.toBeInTheDocument();

    await openTableSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Zobraziť všetko rozbalené" }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&expanded=1$/),
      );
    });
    // Bez klikania na žiadneho klienta — všetci sú rovno rozbalení (#format ako v PDF).
    expect(await screen.findByText("Škôlka - Obed Menu A")).toBeInTheDocument();
  });

  it("pamätá si nastavenie tabuľky aj po odmountovaní (napr. návrat z detailu prevádzky)", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    const first = render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Zobraziť prázdne prevádzky" }));
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&show_empty=0$/),
      );
    });

    // Klik na škôlku odnavigoval preč (AdminDashboard sa odmountuje) a admin
    // sa neskôr vráti späť — nová inštancia sa má správať tak, akoby nikdy
    // neodišiel.
    first.unmount();
    mockApiFetch.mockClear();
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&show_empty=0$/),
      );
    });
    await openTableSettings();
    expect(await screen.findByRole("button", { name: "Zobraziť prázdne prevádzky" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("'Obnoviť predvolené' resets every toggle back to default", async () => {
    mockDashboardRequests(GRAMAGE_WITH_ROWS);
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>);

    await openTableSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Zobraziť prázdne prevádzky" }));
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch&show_empty=0$/),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Obnoviť predvolené" }));
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringMatching(/gramage-dashboard\/\?date=[\d-]+&meal_type=lunch$/),
      );
    });
  });
});
