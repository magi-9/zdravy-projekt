import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ReactNode } from 'react';
import AdminOrderEditorModal from './AdminOrderEditorModal';

// ── Mocks ────────────────────────────────────────────────────────────────────

const mockApiFetch = vi.fn();

vi.mock('../../context/auth', () => ({
    useAuth: vi.fn(() => ({ apiFetch: mockApiFetch })),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
const mockToastInfo = vi.fn();

vi.mock('../../context/ToastContext', () => ({
    useToast: vi.fn(() => ({
        success: mockToastSuccess,
        error: mockToastError,
        warning: vi.fn(),
        info: mockToastInfo,
    })),
    ToastProvider: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

// Keep real OrderService so data-structure helpers work correctly.
// Only mock DietSelector to avoid its internal portal / focus logic in tests.
vi.mock('../client/components/order/DietSelector', () => ({
    default: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
        isOpen ? (
            <div data-testid="diet-selector">
                <button onClick={onClose}>Hotovo</button>
            </div>
        ) : null,
}));

// ── Helpers ──────────────────────────────────────────────────────────────────

const makeMockResponse = (payload: unknown, ok = true) => ({
    ok,
    status: ok ? 200 : 400,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(JSON.stringify(payload)),
    clone() { return makeMockResponse(payload, ok); },
});

const ALL_DIETS = [
    { id: 1, name: 'Bez lepku' },
    { id: 2, name: 'Vegetariánske' },
];

const BASE_PROPS = {
    clientId: '42',
    prevadzkaId: '99',
    visibleMenus: ['A', 'B'],
    visibleMeals: ['breakfast', 'lunch', 'olovrant'],
    visibleDiets: [1],
    portionTypeNames: ['Jasle', 'Škôlka', 'ZŠ 1.stupeň', 'ZŠ 2.stupeň', 'Dospelý (SŠ)'],
    packSeparatelyEnabled: false,
    allDiets: ALL_DIETS,
    existingOrder: null,
    onClose: vi.fn(),
    onSaved: vi.fn(),
};

const getRequestBody = () => {
    const saveCall = mockApiFetch.mock.calls.find(([, options]) =>
        options?.method === 'PATCH' || options?.method === 'POST',
    );
    expect(saveCall).toBeTruthy();
    return JSON.parse(String(saveCall?.[1]?.body));
};

const getCategoryCard = (label: string) => {
    const title = screen.getByText(label);
    const card = title.closest('.zp-cat');
    expect(card).toBeTruthy();
    return card as HTMLElement;
};

const clickFirstPlus = (label: string) => {
    const card = getCategoryCard(label);
    const buttons = within(card).getAllByRole('button', { name: '+' });
    fireEvent.click(buttons[0]);
};

const getMealCard = (title: string) => {
    // Názov chodu sa vyskytuje aj v zhrnutí objednávky — berieme len hlavičku karty.
    const heading = screen
        .getAllByText(title)
        .find((el) => el.closest('.zp-meal-title'));
    const card = heading?.closest('.zp-meal');
    expect(card).toBeTruthy();
    return card as HTMLElement;
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AdminOrderEditorModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockApiFetch.mockResolvedValue(makeMockResponse({ is_closed: false }, true));
    });

    it('renders create mode with date input and save button', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        expect(screen.getByText('Nová objednávka')).toBeInTheDocument();
        expect(screen.getByLabelText(/dátum objednávky/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Uložiť' })).toBeInTheDocument();
    });

    it('shows an emphasized "Dnes" label for today and updates it when the date changes', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-09-02T10:00:00'));
        try {
            render(<AdminOrderEditorModal {...BASE_PROPS} />);

            expect(screen.getByText('Dnes streda 2.9.')).toBeInTheDocument();

            fireEvent.change(screen.getByLabelText(/dátum objednávky/i), { target: { value: '2026-09-03' } });
            expect(screen.getByText('Zajtra štvrtok 3.9.')).toBeInTheDocument();

            fireEvent.change(screen.getByLabelText(/dátum objednávky/i), { target: { value: '2026-09-08' } });
            expect(screen.getByText('Utorok 8.9.')).toBeInTheDocument();
        } finally {
            vi.useRealTimers();
        }
    });

    it('renders edit mode without date input', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{ id: 7, date: '2099-03-01', data: {} }}
            />,
        );

        expect(screen.getByText('Upraviť objednávku')).toBeInTheDocument();
        expect(screen.getByText('2099-03-01')).toBeInTheDocument();
        expect(screen.queryByLabelText(/dátum objednávky/i)).not.toBeInTheDocument();
    });

    it('calls onClose when Zrušiť is clicked', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);
        fireEvent.click(screen.getByRole('button', { name: /zrušiť/i }));
        expect(BASE_PROPS.onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when ✕ icon button is clicked', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);
        // The X button in the header carries the accessible label "Zavrieť".
        const closeBtn = screen.getByRole('button', { name: /zavrieť/i });
        expect(closeBtn).toBeTruthy();
        fireEvent.click(closeBtn);
        expect(BASE_PROPS.onClose).toHaveBeenCalledTimes(1);
    });

    it('POSTs with prevadzka when creating a new order', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 10, date: '2099-05-01', data: {} }, true));

        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            expect(mockApiFetch).toHaveBeenCalledWith(
                expect.stringContaining('/orders/?user_id=42'),
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('"prevadzka":"99"'),
                }),
            );
        });

        // Jarabinka 11.9.2026: admin editor je "nastav celý deň naraz" — každý
        // zobrazený chod je touched, aj keď admin nechal 0, inak by ho
        // auto-order cron mohol ticho doplniť neskôr.
        const postCall = mockApiFetch.mock.calls.find(([, options]) => options?.method === 'POST');
        const body = JSON.parse(postCall![1].body as string);
        expect(body.touched_meals).toEqual(['breakfast', 'lunch', 'olovrant']);

        expect(mockToastSuccess).toHaveBeenCalledWith('Objednávka bola vytvorená.');
        expect(BASE_PROPS.onSaved).toHaveBeenCalledTimes(1);
    });

    it('POSTs with prevadzka without user_id when facility has no login', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 11, date: '2099-05-02', data: {} }, true));

        render(<AdminOrderEditorModal {...BASE_PROPS} clientId={null} />);

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            expect(mockApiFetch).toHaveBeenCalledWith(
                expect.stringContaining('/orders/'),
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('"prevadzka":"99"'),
                }),
            );
        });

        expect(mockApiFetch.mock.calls[0][0]).not.toContain('user_id=');
        expect(mockToastSuccess).toHaveBeenCalledWith('Objednávka bola vytvorená.');
        expect(BASE_PROPS.onSaved).toHaveBeenCalledTimes(1);
    });

    it('PATCHes through prevadzka when editing an existing order', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{ id: 7, date: '2099-03-01', data: {} }}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            expect(mockApiFetch).toHaveBeenCalledWith(
                expect.stringContaining('/orders/7/?prevadzka=99'),
                expect.objectContaining({
                    method: 'PATCH',
                    body: expect.stringContaining('"prevadzka":"99"'),
                }),
            );
        });

        const patchCall = mockApiFetch.mock.calls.find(([, options]) => options?.method === 'PATCH');
        const body = JSON.parse(patchCall![1].body as string);
        expect(body.touched_meals).toEqual(['breakfast', 'lunch', 'olovrant']);

        expect(mockToastSuccess).toHaveBeenCalledWith('Objednávka bola uložená.');
        expect(BASE_PROPS.onSaved).toHaveBeenCalledTimes(1);
    });

    it('preserves packSeparately data when editing an existing order', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2099-03-01',
                    data: {
                        lunch: {
                            Škôlka: {
                                menuCounts: { A: 2, B: 0 },
                                diets: { 'Bez lepku': 0 },
                                packSeparately: { menus: { A: 1 }, diets: {} },
                            },
                        },
                    },
                }}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const patchCall = mockApiFetch.mock.calls.find(([url, options]) =>
                String(url).includes('/orders/7/') && options?.method === 'PATCH',
            );
            expect(patchCall).toBeTruthy();
            const body = JSON.parse(String(patchCall?.[1]?.body));
            expect(body.data.lunch.Škôlka.packSeparately).toEqual({ menus: { A: 1 }, diets: {} });
        });
    });

    it('shows error toast and does not call onSaved when API fails', async () => {
        mockApiFetch.mockImplementation((url: string) => {
            if (url.includes('/admin/closed-days/')) {
                return Promise.resolve(makeMockResponse({ is_closed: false }, true));
            }
            return Promise.reject(new Error('network error'));
        });

        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            expect(mockToastError).toHaveBeenCalledWith('Nepodarilo sa uložiť objednávku.');
        });

        expect(BASE_PROPS.onSaved).not.toHaveBeenCalled();
    });

    it('shows API error message when POST returns 400', async () => {
        const errorResponse = makeMockResponse(
                {
                    error: {
                        message: 'Objednávka na tento dátum už existuje.',
                        details: { date: ['Objednávka na tento dátum už existuje.'] },
                    },
                },
                false,
            );
        mockApiFetch.mockImplementation((url: string) =>
            Promise.resolve(
                url.includes('/admin/closed-days/')
                    ? makeMockResponse({ is_closed: false }, true)
                    : errorResponse,
            ),
        );

        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            expect(mockToastError).toHaveBeenCalledWith('Objednávka na tento dátum už existuje.');
        });

        expect(BASE_PROPS.onSaved).not.toHaveBeenCalled();
    });

    it('renders all three meal cards', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);
        expect(screen.getByText('Raňajky')).toBeInTheDocument();
        expect(screen.getByText('Obed')).toBeInTheDocument();
        expect(screen.getByText('Olovrant')).toBeInTheDocument();
    });

    it('respects visibleMeals prop and hides excluded meals', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} visibleMeals={['lunch']} />);
        expect(screen.queryByText('Raňajky')).not.toBeInTheDocument();
        expect(screen.getByText('Obed')).toBeInTheDocument();
        expect(screen.queryByText('Olovrant')).not.toBeInTheDocument();
    });

    it('hides a meal restricted to another day of the week (raňajky, piatok only, on a Tuesday)', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                mealDayRestrictions={{ breakfast: [5] }}
                existingOrder={{ id: 1, date: '2099-03-03', data: {} }}
            />,
        );
        expect(screen.queryByText('Raňajky')).not.toBeInTheDocument();
        expect(screen.getByText('Obed')).toBeInTheDocument();
        expect(screen.getByText('Olovrant')).toBeInTheDocument();
    });

    it('shows the restricted meal on the day it is allowed (raňajky, piatok only, on a Friday)', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                mealDayRestrictions={{ breakfast: [5] }}
                existingOrder={{ id: 1, date: '2099-03-06', data: {} }}
            />,
        );
        expect(screen.getByText('Raňajky')).toBeInTheDocument();
    });

    it('renders a category present in the order but absent from the hardcoded list and preserves it in the PATCH payload', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2026-07-30',
                    data: {
                        lunch: {
                            Predškolák: {
                                menuCounts: { A: 2 },
                                diets: { 'Bez lepku': 0, 'Špeciálna': 0 },
                            },
                        },
                    },
                }}
            />,
        );

        expect(screen.getByText('Predškolák')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            expect(body.data.lunch.Predškolák.menuCounts.A).toBe(2);
        });
    });

    it('shows the plain menu A count and opens diets from their own row', async () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2026-07-30',
                    // Stará objednávka: A=10 znamenalo „7 bežných + 3 diétne“.
                    data: {
                        lunch: {
                            Škôlka: {
                                menuCounts: { A: 10 },
                                diets: { 'Bez lepku': 3 },
                            },
                        },
                    },
                }}
            />,
        );

        const lunchCard = getMealCard('Obed');
        const skolkaCard = within(lunchCard).getByText('Škôlka').closest('.zp-cat') as HTMLElement;

        const menuAInput = within(skolkaCard).getByLabelText('Počet porcií pre menu A');
        expect((menuAInput as HTMLInputElement).value).toBe('7');

        const dietButton = within(skolkaCard).getByRole('button', { name: /Diéty/ });
        expect(dietButton).toHaveTextContent('3');

        fireEvent.click(dietButton);
        expect(await screen.findByTestId('diet-selector')).toBeInTheDocument();
    });

    it('adds diets on top of the plain menu A count in the payload', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2026-07-30',
                    data: {
                        lunch: {
                            Škôlka: { menuCounts: { A: 4 }, diets: { 'Bez lepku': 1 } },
                        },
                    },
                }}
            />,
        );

        const lunchCard = getMealCard('Obed');
        const skolkaCard = within(lunchCard).getByText('Škôlka').closest('.zp-cat') as HTMLElement;

        // 3 bežné porcie (4 − 1 diéta) navýšime na 4 => uloží sa 4 + 1 = 5.
        const menuAInput = within(skolkaCard).getByLabelText('Počet porcií pre menu A');
        expect((menuAInput as HTMLInputElement).value).toBe('3');
        fireEvent.change(menuAInput, { target: { value: '4' } });
        fireEvent.blur(menuAInput);

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            expect(body.data.lunch.Škôlka.menuCounts.A).toBe(5);
            expect(body.data.lunch.Škôlka.diets['Bez lepku']).toBe(1);
        });
    });

    it('preserves special_diet_note in the PATCH payload when saving without editing it', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2026-07-30',
                    data: {
                        lunch: {
                            Škôlka: {
                                menuCounts: { A: 1 },
                                diets: { 'Bez lepku': 0, 'Špeciálna': 1 },
                            },
                        },
                        special_diet_note: 'Bez paradajok',
                    },
                }}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            expect(body.data.special_diet_note).toBe('Bez paradajok');
        });
    });

    it('updates special_diet_note in the saved payload when the textarea is edited', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{
                    id: 7,
                    date: '2026-07-30',
                    data: {
                        lunch: {
                            Škôlka: {
                                menuCounts: { A: 1 },
                                diets: { 'Bez lepku': 0, 'Špeciálna': 1 },
                            },
                        },
                    },
                }}
            />,
        );

        fireEvent.change(screen.getByPlaceholderText(/popíšte vašu špeciálnu diétu/i), {
            target: { value: 'Bez mlieka a vajec' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            expect(body.data.special_diet_note).toBe('Bez mlieka a vajec');
        });
    });

    it('renders pack-separately UI only when enabled and saves changes under packSeparately', async () => {
        mockApiFetch.mockResolvedValue(makeMockResponse({ id: 7 }, true));

        const existingOrder = {
            id: 7,
            date: '2026-07-30',
            data: {
                lunch: {
                    Škôlka: {
                        menuCounts: { A: 2, B: 0 },
                        diets: { 'Bez lepku': 1, 'Špeciálna': 0 },
                    },
                },
            },
        };

        const { rerender } = render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                packSeparatelyEnabled={false}
                existingOrder={existingOrder}
            />,
        );

        expect(screen.queryByText('Zabaliť zvlášť')).not.toBeInTheDocument();

        rerender(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                packSeparatelyEnabled={true}
                existingOrder={existingOrder}
            />,
        );

        expect(screen.getByText('Zabaliť zvlášť')).toBeInTheDocument();

        // Karta je zbalená, kým nie je nič označené, takže tlačidlo „Zabaliť zvlášť“
        // ešte neexistuje — selector sa otvára prepínačom v hlavičke karty (rovnako
        // ako na klientskej strane).
        fireEvent.click(screen.getByRole('switch', { name: /Zabaliť zvlášť - prepnúť/i }));

        // „+“ je aj v riadkoch kategórií, tak sa držíme vnútra otvoreného selectora.
        const sheet = screen.getByRole('heading', { name: 'Zabaliť zvlášť' }).closest('.zp-sheet') as HTMLElement;
        const row = within(sheet).getByText(/Škôlka · Menu A/i).closest('.zp-diet-row') as HTMLElement;
        fireEvent.click(within(row).getByLabelText('+'));
        fireEvent.click(within(sheet).getByLabelText('Zavrieť'));
        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            // `cleanupPackSeparately` zahodí celý objekt až keď sú prázdne obe vetvy,
            // takže prázdne `diets` tu zostáva.
            expect(body.data.lunch.Škôlka.packSeparately).toEqual({ menus: { A: 1 }, diets: {} });
        });
    });

    it('replicates the single full-day MealData into every visible meal in the saved payload', async () => {
        mockApiFetch.mockResolvedValueOnce(makeMockResponse({ id: 7 }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                visibleMeals={['breakfast', 'olovrant']}
                existingOrder={{ id: 7, date: '2026-07-30', data: {} }}
            />,
        );

        fireEvent.click(screen.getByRole('switch', { name: /celodenná objednávka - prepnúť/i }));
        clickFirstPlus('Škôlka');
        fireEvent.click(screen.getByRole('button', { name: 'Uložiť' }));

        await waitFor(() => {
            const body = getRequestBody();
            expect(body.data.breakfast.Škôlka.menuCounts.A).toBe(1);
            expect(body.data.olovrant.Škôlka.menuCounts.A).toBe(1);
            expect(body.data.lunch.Škôlka.menuCounts.A).toBe(0);
        });
    });

    it('shows only menu A for breakfast and olovrant, while lunch keeps configured menus', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        // Karta chodu renderuje countery až keď je chod zapnutý.
        ['Raňajky', 'Obed', 'Olovrant'].forEach((meal) => {
            fireEvent.click(screen.getByRole('switch', { name: new RegExp(`${meal} - prepnúť`, 'i') }));
        });

        const breakfastCard = getMealCard('Raňajky');
        const lunchCard = getMealCard('Obed');
        const olovrantCard = getMealCard('Olovrant');

        // Raňajky/olovrant: 5 kategórií × iba menu A.
        expect(within(breakfastCard).getAllByRole('button', { name: '+' })).toHaveLength(5);
        expect(within(olovrantCard).getAllByRole('button', { name: '+' })).toHaveLength(5);
        // Obed: kategória menu neobmedzuje, len prevádzka — visibleMenus ['A','B']
        // pre všetkých 5 kategórií = 10.
        expect(within(lunchCard).getAllByRole('button', { name: '+' })).toHaveLength(10);
    });

    it('hides a menu restricted to another day of the week (Menu B, piatok only, on a Tuesday)', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                menuDayRestrictions={{ B: [5] }}
                existingOrder={{ id: 1, date: '2099-03-03', data: {} }}
            />,
        );
        fireEvent.click(screen.getByRole('switch', { name: /obed - prepnúť/i }));

        const lunchCard = getMealCard('Obed');
        // Bez Menu B: Jasle/Škôlka/ZŠ1/ZŠ2/Dospelý po jednom (len Menu A) = 5.
        expect(within(lunchCard).getAllByRole('button', { name: '+' })).toHaveLength(5);
    });

    it('shows the restricted menu on the day it is allowed (Menu B, piatok only, on a Friday)', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                menuDayRestrictions={{ B: [5] }}
                existingOrder={{ id: 1, date: '2099-03-06', data: {} }}
            />,
        );
        fireEvent.click(screen.getByRole('switch', { name: /obed - prepnúť/i }));

        const lunchCard = getMealCard('Obed');
        expect(within(lunchCard).getAllByRole('button', { name: '+' })).toHaveLength(10);
    });

    it('shows the full-day card and, once enabled, keeps meal cards visible with full-day status', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        expect(screen.getByText('Celodenná objednávka')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('switch', { name: /celodenná objednávka - prepnúť/i }));

        expect(screen.getByText(/bude objednané:/i)).toBeInTheDocument();
        expect(screen.getAllByText('Celodenná objednávka je aktívna')).toHaveLength(3);
        expect(screen.getByText('Raňajky')).toBeInTheDocument();
        expect(screen.getByText('Obed')).toBeInTheDocument();
        expect(screen.getByText('Olovrant')).toBeInTheDocument();
    });

    it('copies counts from lunch into olovrant via "Kopírovať z obeda"', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        fireEvent.click(screen.getByRole('switch', { name: /obed - prepnúť/i }));
        fireEvent.click(screen.getByRole('switch', { name: /olovrant - prepnúť/i }));

        const lunchCard = getMealCard('Obed');
        // Kategória "Škôlka" je v každej otvorenej karte chodu — scope na obed.
        const lunchCategory = within(lunchCard).getByText('Škôlka').closest('.zp-cat') as HTMLElement;
        fireEvent.click(within(lunchCategory).getAllByRole('button', { name: '+' })[0]);
        expect(within(lunchCard).getAllByDisplayValue('1').length).toBeGreaterThan(0);

        fireEvent.click(screen.getByRole('button', { name: /kopírovať z obeda/i }));

        const olovrantCard = getMealCard('Olovrant');
        expect(within(olovrantCard).getAllByDisplayValue('1').length).toBeGreaterThan(0);
    });

    it('resets a meal when "Vymazať" is clicked', () => {
        render(<AdminOrderEditorModal {...BASE_PROPS} />);

        fireEvent.click(screen.getByRole('switch', { name: /raňajky - prepnúť/i }));
        const breakfastCategory = getCategoryCard('Škôlka');
        fireEvent.click(within(breakfastCategory).getAllByRole('button', { name: '+' })[0]);

        const breakfastCard = getMealCard('Raňajky');
        expect(within(breakfastCard).getAllByDisplayValue('1').length).toBeGreaterThan(0);

        fireEvent.click(screen.getByRole('button', { name: /^vymazať$/i }));

        expect(within(breakfastCard).queryByDisplayValue('1')).not.toBeInTheDocument();
    });

    it('loads breakfast from the previous day\'s lunch via "Načítať z včerajška"', () => {
        const prevLunch = {
            'Škôlka': { menuCounts: { A: 3 }, diets: {} },
        };

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{ id: 7, date: '2099-03-02', data: {} }}
                knownOrders={[{ id: 6, date: '2099-03-01', data: { lunch: prevLunch } }]}
            />,
        );

        fireEvent.click(screen.getByRole('switch', { name: /raňajky - prepnúť/i }));
        fireEvent.click(screen.getByRole('button', { name: /načítať z včerajška/i }));

        const breakfastCard = getMealCard('Raňajky');
        expect(within(breakfastCard).getAllByDisplayValue('3').length).toBeGreaterThan(0);
        expect(mockToastSuccess).toHaveBeenCalledWith('Raňajky načítané z obeda (včera).');
    });

    it('reports missing data when the previous day has no lunch', () => {
        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{ id: 7, date: '2099-03-02', data: {} }}
                knownOrders={[]}
            />,
        );

        fireEvent.click(screen.getByRole('switch', { name: /raňajky - prepnúť/i }));
        fireEvent.click(screen.getByRole('button', { name: /načítať z včerajška/i }));

        expect(mockToastInfo).toHaveBeenCalledWith('Nemám dáta z včerajšieho obeda.');
    });

    it('shows a read-only blocked state when the order date is closed', async () => {
        mockApiFetch.mockResolvedValue(makeMockResponse({ is_closed: true }, true));

        render(
            <AdminOrderEditorModal
                {...BASE_PROPS}
                existingOrder={{ id: 7, date: '2099-03-01', data: {} }}
            />,
        );

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'Deň je uzavretý, objednávky sa už nedajú upravovať.',
        );
        expect(screen.queryByRole('button', { name: 'Uložiť' })).not.toBeInTheDocument();
        expect(screen.queryByText('Celodenná objednávka')).not.toBeInTheDocument();
    });
});
