import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DietManager from "./DietManager";

const mockApiFetch = vi.fn();
const mockToastError = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

vi.mock("../../context/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: mockToastError }),
}));

const response = (payload: unknown) => ({ ok: true, json: async () => payload });

describe("DietManager diet numbering", () => {
  it("shows the first diet as position 1, not 0, even when sort_order is 0-based", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/diets/")) {
        return Promise.resolve(response([
          { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "" },
          { id: 2, name: "Vegán", sort_order: 0, is_active: true, description: "" },
        ]));
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    const firstCard = (await screen.findByText("Bezlepková")).closest(".zpa-diet-card")!;
    const secondCard = screen.getByText("Vegán").closest(".zpa-diet-card")!;

    expect(firstCard).toHaveTextContent("Poradie: 1");
    expect(secondCard).toHaveTextContent("Poradie: 2");
    expect(firstCard).not.toHaveTextContent("Poradie: 0");
  });

  it("has no manual poradie input — new diets are placed automatically", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/diets/")) {
        return Promise.resolve(response([
          { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "" },
        ]));
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await screen.findByText("Bezlepková");
    expect(screen.queryByLabelText("Poradie")).not.toBeInTheDocument();
    expect(screen.queryByText("Poradie")).not.toBeInTheDocument();
  });

  it("appends a new diet to the end of its own component-count block, not the whole list", async () => {
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/diets/") && init?.method === "POST") {
        const body = JSON.parse(init.body as string);
        return Promise.resolve(
          response({ id: 99, is_active: true, base_diets: [], ...body }),
        );
      }
      if (url.includes("/diets/")) {
        return Promise.resolve(response([
          { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "", base_diets: [] },
          { id: 2, name: "Bez laktózy", sort_order: 3, is_active: true, description: "", base_diets: [] },
          // Composite diet sitting after the single-component block in sort_order —
          // the new single-component diet must not be appended after this one.
          { id: 3, name: "Bezlepková – Bez laktózy", sort_order: 10, is_active: true, description: "", base_diets: [1, 2] },
        ]));
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await screen.findByText("Bezlepková");
    fireEvent.change(screen.getByPlaceholderText("Názov novej diéty (napr. Bez lepku)"), {
      target: { value: "Vegán" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Pridať diétu/ }));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        ([, init]) => init?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      const body = JSON.parse(postCall![1].body as string);
      expect(body.sort_order).toBe(4);
    });
  });

  it("groups diets into 1-/2-zložkové sections by number of base diets", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/diets/")) {
        return Promise.resolve(response([
          { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "", base_diets: [] },
          { id: 2, name: "Bez laktózy", sort_order: 1, is_active: true, description: "", base_diets: [] },
          { id: 3, name: "Bezlepková – Bez laktózy", sort_order: 2, is_active: true, description: "", base_diets: [1, 2] },
        ]));
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await screen.findByText("Bezlepková");
    expect(screen.getByText("1-zložkové", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("2-zložkové", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("3-zložkové", { exact: false })).not.toBeInTheDocument();
  });
});

describe("DietManager text/background colour picker (#536)", () => {
  const chooseColour = async (label: string, colour: string) => {
    await userEvent.click(screen.getByRole("button", { name: `Vybrať ${label}` }));
    const colourModal = within(screen.getByRole("dialog", { name: label }));
    await userEvent.click(colourModal.getByRole("button", { name: `${label}: ${colour}` }));
  };

  it("shows a live preview and saves an explicit text/background colour for a new diet", async () => {
    let createBody: Record<string, unknown> | undefined;
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/diets/") && init?.method === "POST") {
        createBody = JSON.parse(init.body as string);
        return Promise.resolve(
          response({ id: 3, name: "Bez vajec", sort_order: 0, is_active: true, description: "" }),
        );
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await userEvent.type(
      await screen.findByPlaceholderText("Názov novej diéty (napr. Bez lepku)"),
      "Bez vajec",
    );

    // Náhľad je vždy vidno, aj bez výberu (ukazuje počítanú predvolenú farbu).
    expect(screen.getByTestId("diet-style-preview")).toHaveTextContent("Bez vajec");

    // Paleta nezaberá miesto vo formulári — otvorí sa až z kompaktného tlačidla.
    expect(screen.queryByRole("group", { name: "Farba textu v PDF" })).not.toBeInTheDocument();
    await chooseColour("Farba textu v PDF", "#31D8D8");
    expect(screen.queryByRole("dialog", { name: "Farba textu v PDF" })).not.toBeInTheDocument();
    await chooseColour("Farba pozadia v PDF", "#D8D831");
    await userEvent.click(screen.getByRole("button", { name: "Pridať diétu" }));

    expect(createBody).toMatchObject({
      name: "Bez vajec",
      text_color: "#31D8D8",
      background_color: "#D8D831",
    });
  });

  it("pre-fills the pickers from the diet being edited and saves the change", async () => {
    let patchBody: Record<string, unknown> | undefined;
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/diets/") && init?.method === "PATCH") {
        patchBody = JSON.parse(init.body as string);
        return Promise.resolve(response({}));
      }
      if (url.includes("/diets/")) {
        return Promise.resolve(
          response([
            {
              id: 1,
              name: "Bezlepková",
              sort_order: 0,
              is_active: true,
              description: "",
              color: "#F59E0B",
              text_color: "#111111",
              background_color: "#EEEEEE",
            },
          ]),
        );
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByTitle("Upraviť"));
    const modal = within(screen.getByText("Upraviť diétu").closest(".zpa-modal") as HTMLElement);
    // Pred akoukoľvek zmenou je "Uložiť" zablokované (žiadny rozdiel oproti
    // uloženej diéte) - dokazuje, že pickery boli správne predvyplnené.
    expect(modal.getByRole("button", { name: "Uložiť" })).toBeDisabled();

    await userEvent.click(modal.getByRole("button", { name: "Vybrať Farba textu v PDF" }));
    const colourModal = within(screen.getByRole("dialog", { name: "Farba textu v PDF" }));
    await userEvent.click(colourModal.getByRole("button", { name: "Farba textu v PDF: #D831D8" }));
    await userEvent.click(modal.getByRole("button", { name: "Uložiť" }));

    expect(patchBody).toMatchObject({
      text_color: "#D831D8",
      background_color: "#EEEEEE",
    });
  });

  it("creates a combined diet in two steps: composition first, colours second", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/diets/")) {
        return Promise.resolve(
          response([
            { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "", base_diets: [] },
            { id: 2, name: "Bez laktózy", sort_order: 1, is_active: true, description: "", base_diets: [] },
          ]),
        );
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await screen.findByText("Bezlepková");

    // Bežná diéta má dve tlačidlá, žiadne stále rozbalené palety ani tretí picker.
    expect(screen.queryByRole("group", { name: "Farba novej diéty" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vybrať Farba textu v PDF" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vybrať Farba pozadia v PDF" })).toBeInTheDocument();

    // Krok 1 obsahuje iba zloženie kombinácie.
    await userEvent.click(screen.getByRole("button", { name: /Vytvoriť kombinovanú/ }));
    const compositeModal = within(
      screen.getByText("Vytvoriť kombinovanú diétu").closest(".zpa-modal") as HTMLElement,
    );
    expect(compositeModal.getByText("Krok 1 z 2")).toBeInTheDocument();
    expect(compositeModal.queryByRole("button", { name: "Vybrať Farba textu v PDF" })).not.toBeInTheDocument();
    expect(compositeModal.getByRole("button", { name: "Pokračovať na farby" })).toBeDisabled();

    await userEvent.click(compositeModal.getByRole("button", { name: /Bezlepková/ }));
    await userEvent.click(compositeModal.getByRole("button", { name: /Bez laktózy/ }));

    await userEvent.click(compositeModal.getByRole("button", { name: "Pokračovať na farby" }));

    // Krok 2 obsahuje už iba farby a náhľad; dá sa z neho vrátiť späť.
    expect(compositeModal.getByText("Krok 2 z 2")).toBeInTheDocument();
    expect(compositeModal.queryByRole("button", { name: /Bezlepková/ })).not.toBeInTheDocument();
    expect(compositeModal.getByRole("button", { name: "Vybrať Farba textu v PDF" })).toBeInTheDocument();
    expect(compositeModal.getByRole("button", { name: "Vybrať Farba pozadia v PDF" })).toBeInTheDocument();
    expect(compositeModal.getByTestId("diet-style-preview")).toBeInTheDocument();
    expect(compositeModal.getByRole("button", { name: "Späť" })).toBeInTheDocument();

    await userEvent.click(compositeModal.getByRole("button", { name: "Zavrieť" }));
    await userEvent.click(screen.getAllByTitle("Upraviť")[0]);
    const editModal = within(screen.getByText("Upraviť diétu").closest(".zpa-modal") as HTMLElement);
    expect(editModal.queryByRole("group", { name: /^Farba diéty/ })).not.toBeInTheDocument();
    expect(editModal.getByRole("button", { name: "Vybrať Farba textu v PDF" })).toBeInTheDocument();
    expect(editModal.getByRole("button", { name: "Vybrať Farba pozadia v PDF" })).toBeInTheDocument();
  });

  it("surfaces the server's validation message instead of a generic guess (#name too long, 10.9.2026)", async () => {
    mockToastError.mockClear();
    mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/diets/") && init?.method === "POST") {
        return Promise.resolve({
          ok: false,
          json: async () => ({
            name: ["Ensure this field has no more than 255 characters."],
          }),
        });
      }
      if (url.includes("/diets/")) {
        return Promise.resolve(
          response([
            { id: 1, name: "Bezlepková", sort_order: 0, is_active: true, description: "", base_diets: [] },
            { id: 2, name: "Bez laktózy", sort_order: 1, is_active: true, description: "", base_diets: [] },
          ]),
        );
      }
      return Promise.resolve(response([]));
    });

    render(
      <MemoryRouter>
        <DietManager />
      </MemoryRouter>,
    );

    await screen.findByText("Bezlepková");
    await userEvent.click(screen.getByRole("button", { name: /Vytvoriť kombinovanú/ }));
    const compositeModal = within(
      screen.getByText("Vytvoriť kombinovanú diétu").closest(".zpa-modal") as HTMLElement,
    );
    await userEvent.click(compositeModal.getByRole("button", { name: /Bezlepková/ }));
    await userEvent.click(compositeModal.getByRole("button", { name: /Bez laktózy/ }));
    await userEvent.click(compositeModal.getByRole("button", { name: "Pokračovať na farby" }));
    await userEvent.click(compositeModal.getByRole("button", { name: "Vytvoriť kombináciu" }));

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith(
        "Ensure this field has no more than 255 characters.",
      ),
    );
  });
});
