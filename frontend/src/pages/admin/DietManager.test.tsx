import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DietManager from "./DietManager";

const mockApiFetch = vi.fn();

vi.mock("../../context/auth", () => ({
  useAuth: () => ({ apiFetch: mockApiFetch }),
}));

vi.mock("../../context/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
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

    await userEvent.click(screen.getByRole("button", { name: "Farba textu v PDF: #31D8D8" }));
    await userEvent.click(screen.getByRole("button", { name: "Farba pozadia v PDF: #D8D831" }));
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

    await userEvent.click(modal.getByRole("button", { name: "Farba textu v PDF: #D831D8" }));
    await userEvent.click(modal.getByRole("button", { name: "Uložiť" }));

    expect(patchBody).toMatchObject({
      text_color: "#D831D8",
      background_color: "#EEEEEE",
    });
  });

  it("shows exactly two colour pickers (text + background) — no separate base colour picker", async () => {
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

    // Formulár pridania novej diéty: len 2 pickery (text + pozadie), žiadna
    // samostatná "Farba" navyše.
    expect(screen.queryByRole("group", { name: "Farba novej diéty" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Farba textu v PDF" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Farba pozadia v PDF" })).toBeInTheDocument();

    // Kombinovaná diéta má tie isté 2 pickery + náhľad, nie navyše.
    await userEvent.click(screen.getByRole("button", { name: /Vytvoriť kombinovanú/ }));
    const compositeModal = within(
      screen.getByText("Vytvoriť kombinovanú diétu").closest(".zpa-modal") as HTMLElement,
    );
    await userEvent.click(compositeModal.getByRole("button", { name: /Bezlepková/ }));
    await userEvent.click(compositeModal.getByRole("button", { name: /Bez laktózy/ }));
    expect(compositeModal.getByRole("group", { name: "Farba textu v PDF" })).toBeInTheDocument();
    expect(compositeModal.getByRole("group", { name: "Farba pozadia v PDF" })).toBeInTheDocument();
    expect(compositeModal.getByTestId("diet-style-preview")).toBeInTheDocument();

    // Úprava existujúcej (nekombinovanej) diéty: rovnako len 2 pickery.
    await userEvent.click(screen.getByRole("button", { name: "Zrušiť" }));
    await userEvent.click(screen.getAllByTitle("Upraviť")[0]);
    const editModal = within(screen.getByText("Upraviť diétu").closest(".zpa-modal") as HTMLElement);
    expect(editModal.queryByRole("group", { name: /^Farba diéty/ })).not.toBeInTheDocument();
    expect(editModal.getByRole("group", { name: "Farba textu v PDF" })).toBeInTheDocument();
    expect(editModal.getByRole("group", { name: "Farba pozadia v PDF" })).toBeInTheDocument();
  });
});
