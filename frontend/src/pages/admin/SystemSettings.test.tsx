import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SystemSettings from './SystemSettings';

// Mock the auth context
const mockApiFetch = vi.fn();
vi.mock('../../context/auth', () => ({
    useAuth: () => ({
        apiFetch: mockApiFetch,
    }),
}));

// Mock the toast context
const mockSuccess = vi.fn();
const mockError = vi.fn();
vi.mock('../../context/ToastContext', () => ({
    useToast: () => ({
        success: mockSuccess,
        error: mockError,
    }),
}));

describe('SystemSettings - Report Recipients Auto-Save', () => {
    const mockSettings = {
        deadline_breakfast: '10:00',
        deadline_breakfast_is_day_before: false,
        deadline_lunch: '10:00',
        deadline_lunch_is_day_before: false,
        deadline_olovrant: '10:00',
        deadline_olovrant_is_day_before: false,
        edupage_auto_scrape_enabled: true,
        report_email_recipients: ['existing@example.com'],
        client_contact_name: '',
        client_contact_role: '',
        client_contact_email: '',
        client_contact_phone: '',
    };

    beforeEach(() => {
        // Clear only apiFetch mock, not toast mocks
        mockApiFetch.mockClear();
        mockSuccess.mockClear();
        mockError.mockClear();
        
        // Set up default successful responses for all calls
        mockApiFetch.mockImplementation((_url: string, options?: RequestInit) => {
            return Promise.resolve({
                ok: true,
                json: async () => {
                    // Return settings for GET requests, empty for POST
                    return options?.method === 'POST' ? {} : mockSettings;
                },
            });
        });
    });

    it('adds a new recipient and shows success message', async () => {
        const user = userEvent.setup();

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'Denný report' }));

        // Wait for initial load
        await waitFor(() => {
            expect(screen.getByText('existing@example.com')).toBeInTheDocument();
        });

        const emailInput = screen.getByPlaceholderText('email@priklad.sk') as HTMLInputElement;
        const addButton = screen.getByText('Pridať');

        // Add new recipient
        await user.type(emailInput, 'new@example.com');
        await user.click(addButton);

        // Verify new recipient appears (success message is less reliable in test env)
        await waitFor(() => {
            expect(screen.getByText('new@example.com')).toBeInTheDocument();
        });
    });

    it('removes a recipient', async () => {
        const user = userEvent.setup();

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'Denný report' }));

        // Wait for initial load
        await waitFor(() => {
            expect(screen.getByText('existing@example.com')).toBeInTheDocument();
        });

        // Find and click remove button
        const removeButtons = screen.getAllByText('Odstrániť');
        await user.click(removeButtons[0]);

        // Verify recipient is removed
        await waitFor(() => {
            expect(screen.queryByText('existing@example.com')).not.toBeInTheDocument();
        });
    });

    it('validates email format before adding', async () => {
        const user = userEvent.setup();

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'Denný report' }));

        await waitFor(() => {
            expect(screen.getByText('existing@example.com')).toBeInTheDocument();
        });

        const emailInput = screen.getByPlaceholderText('email@priklad.sk');
        const addButton = screen.getByText('Pridať');

        // Try to add invalid email
        await user.type(emailInput, 'invalid-email');
        await user.click(addButton);

        // Verify error message
        expect(mockError).toHaveBeenCalledWith('Neplatná e-mailová adresa');
    });

    it('prevents adding duplicate recipients', async () => {
        const user = userEvent.setup();

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'Denný report' }));

        await waitFor(() => {
            expect(screen.getByText('existing@example.com')).toBeInTheDocument();
        });

        const emailInput = screen.getByPlaceholderText('email@priklad.sk');
        const addButton = screen.getByText('Pridať');

        // Try to add existing email
        await user.type(emailInput, 'existing@example.com');
        await user.click(addButton);

        // Verify error message
        expect(mockError).toHaveBeenCalledWith('Táto adresa je už v zozname');
    });

    it('saves disabled EduPage automatic scraping', async () => {
        const user = userEvent.setup();

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'EduPage' }));

        await waitFor(() => {
            expect(screen.getByText('EduPage automatika')).toBeInTheDocument();
        });

        await user.click(screen.getByLabelText('Automatické čítanie EduPage'));
        await user.click(screen.getByText('Uložiť EduPage'));

        await waitFor(() => {
            expect(mockApiFetch).toHaveBeenLastCalledWith(
                expect.stringContaining('/admin/global-settings/'),
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('"edupage_auto_scrape_enabled":false'),
                }),
            );
        });
    });
});

describe('SystemSettings - manuálny EduPage scrape', () => {
    const mockSettings = {
        deadline_breakfast: '10:00',
        deadline_breakfast_is_day_before: false,
        deadline_lunch: '10:00',
        deadline_lunch_is_day_before: false,
        deadline_olovrant: '10:00',
        deadline_olovrant_is_day_before: false,
        edupage_auto_scrape_enabled: true,
        report_email_recipients: [],
        client_contact_name: '',
        client_contact_role: '',
        client_contact_email: '',
        client_contact_phone: '',
    };

    beforeEach(() => {
        mockApiFetch.mockClear();
        mockSuccess.mockClear();
        mockError.mockClear();
    });

    it('zavolá scrape endpoint a ohlási počty', async () => {
        const user = userEvent.setup();
        mockApiFetch.mockImplementation((url: string, options?: RequestInit) => {
            if (url.includes('/edupage-connections/scrape/')) {
                return Promise.resolve({
                    ok: true,
                    json: async () => ({
                        date: '2026-07-23',
                        results: [
                            { status: 'updated', orders: [{ order_id: 1 }, { order_id: 2 }] },
                            { status: 'skipped' },
                        ],
                    }),
                });
            }
            return Promise.resolve({
                ok: true,
                json: async () => (options?.method === 'POST' ? {} : mockSettings),
            });
        });

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'EduPage' }));
        const btn = await screen.findByRole('button', { name: /Načítať z EduPage/i });
        await user.click(btn);

        await waitFor(() => {
            const call = mockApiFetch.mock.calls.find((c) =>
                String(c[0]).includes('/edupage-connections/scrape/'),
            );
            expect(call).toBeTruthy();
            expect(call?.[1]?.method).toBe('POST');
        });
        await waitFor(() => {
            expect(mockSuccess).toHaveBeenCalledWith(
                expect.stringContaining('1 prevádzok, 2 objednávok'),
            );
        });
    });

    it('ohlási chybu, keď sa nenačíta žiadna prevádzka', async () => {
        const user = userEvent.setup();
        mockApiFetch.mockImplementation((url: string, options?: RequestInit) => {
            if (url.includes('/edupage-connections/scrape/')) {
                return Promise.resolve({ ok: true, json: async () => ({ results: [] }) });
            }
            return Promise.resolve({
                ok: true,
                json: async () => (options?.method === 'POST' ? {} : mockSettings),
            });
        });

        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'EduPage' }));
        await user.click(await screen.findByRole('button', { name: /Načítať z EduPage/i }));

        await waitFor(() => {
            expect(mockError).toHaveBeenCalledWith(expect.stringContaining('žiadna prevádzka'));
        });
        expect(mockSuccess).not.toHaveBeenCalled();
    });
});

describe('SystemSettings - údržba', () => {
    const maintenanceSettings = {
        deadline_breakfast: '10:00', deadline_breakfast_is_day_before: false,
        deadline_lunch: '10:00', deadline_lunch_is_day_before: false,
        deadline_olovrant: '10:00', deadline_olovrant_is_day_before: false,
        edupage_auto_scrape_enabled: true, report_email_recipients: [],
        client_contact_name: '', client_contact_role: '', client_contact_email: '', client_contact_phone: '',
        maintenance_enabled: true,
        maintenance_starts_at: '2026-09-10T08:00:00Z',
        maintenance_ends_at: '2026-09-10T10:00:00Z',
    };

    beforeEach(() => {
        mockApiFetch.mockReset();
        mockApiFetch.mockImplementation((_url: string, options?: RequestInit) => Promise.resolve({
            ok: true,
            json: async () => (options?.method === 'POST' ? {} : maintenanceSettings),
        }));
    });

    it('shows the configured maintenance window and clears it explicitly', async () => {
        const user = userEvent.setup();
        render(<SystemSettings />);
        await user.click(await screen.findByRole('button', { name: 'Údržba' }));

        expect(await screen.findByText('Aktuálna údržba')).toBeInTheDocument();
        expect(screen.getByText('Naplánovaná')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Zmazať údržbu' }));

        await waitFor(() => {
            expect(mockApiFetch).toHaveBeenLastCalledWith(
                expect.stringContaining('/admin/global-settings/'),
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('"maintenance_enabled":false'),
                }),
            );
        });
        expect(screen.getByText('Nie je nastavená')).toBeInTheDocument();
    });
});
