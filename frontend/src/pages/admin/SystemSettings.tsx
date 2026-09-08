import React, { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { useAuth } from '../../context/auth';
import { useToast } from '../../context/ToastContext';
import { logger } from '../../lib/logger';
import { SECTION, canRead } from '../../lib/sections';
import { PageHead, Card, CardHead, Button, Field, Input, Toggle } from './ui';

type SettingsTab = 'deadlines' | 'edupage' | 'contact' | 'report' | 'maintenance';

const TABS: { key: SettingsTab; label: string }[] = [
    { key: 'deadlines', label: 'Časy' },
    { key: 'edupage', label: 'EduPage' },
    { key: 'contact', label: 'Kontakt' },
    { key: 'report', label: 'Denný report' },
    { key: 'maintenance', label: 'Údržba' },
];

// Priateľský slovenský názov pre needitovateľný prehľad automatických behov
// nižšie v tabe „Časy" — rovnaký princíp ako `TASK_LABELS_SK` v AdminLogs.tsx
// (samostatná kópia, nech tab nezávisí od inej admin stránky).
const AUTOMATION_TASK_LABELS_SK: Record<string, string> = {
    'api.tasks.scrape_edupage_orders_task': 'EduPage scrape',
    'api.tasks.send_push_deadline_reminder_task': 'Push pripomienka',
    'api.tasks.send_weekly_order_reminder_task': 'Týždenná pripomienka',
    'api.tasks.apply_auto_orders_task': 'Auto-objednávky',
    'api.tasks.send_daily_report_task': 'Denný report',
    'api.tasks.purge_old_event_logs_task': 'Čistenie starých záznamov',
    'celery.backend_cleanup': 'Interná Celery úloha',
};

interface UpcomingEventEntry {
    name: string;
    task: string;
    description: string;
    next_run: string | null;
}

interface EdupageConnection {
    id: number;
    name: string;
    mealsguest_url: string;
    api_identifier: string;
    is_active: boolean;
}

interface ScrapeResult {
    connection_id: number;
    name: string;
    status: string;
    reason?: string;
    error?: string;
    warnings?: string[];
    unmapped_letters?: string[];
    config_notes?: string[];
    attention?: string[];
    orders?: { prevadzka: string; status: string; order_id: number }[];
}

interface GlobalSettings {
    maintenance_enabled: boolean;
    maintenance_starts_at: string | null;
    maintenance_ends_at: string | null;
    deadline_breakfast: string;
    deadline_breakfast_is_day_before: boolean;
    deadline_lunch: string;
    deadline_lunch_is_day_before: boolean;
    deadline_olovrant: string;
    deadline_olovrant_is_day_before: boolean;
    edupage_auto_scrape_enabled: boolean;
    // Voliteľné rozpojenie uzávierky objednávok a času, kedy sa naozaj
    // scrapuje EduPage (napr. uzávierka 21:00 večer predtým, scrape až
    // 1:35 ráno v deň jedla). `null` = scrape beží presne pri uzávierke.
    edupage_scrape_time_breakfast: string | null;
    edupage_scrape_time_breakfast_is_day_before: boolean;
    edupage_scrape_time_lunch: string | null;
    edupage_scrape_time_lunch_is_day_before: boolean;
    edupage_scrape_time_olovrant: string | null;
    edupage_scrape_time_olovrant_is_day_before: boolean;
    daily_report_enabled: boolean;
    report_email_recipients: string[];
    client_contact_name: string;
    client_contact_role: string;
    client_contact_email: string;
    client_contact_phone: string;
}

const SystemSettings: React.FC = () => {
    const { apiFetch, user } = useAuth();
    const { success, error } = useToast();
    const canSeeAutomation = canRead(user?.sections, SECTION.nadchadzajuce);
    const [automation, setAutomation] = useState<UpcomingEventEntry[]>([]);
    const [automationLoading, setAutomationLoading] = useState(true);
    const [settings, setSettings] = useState<GlobalSettings>({
        maintenance_enabled: false,
        maintenance_starts_at: null,
        maintenance_ends_at: null,
        deadline_breakfast: '10:00',
        deadline_breakfast_is_day_before: false,
        deadline_lunch: '10:00',
        deadline_lunch_is_day_before: false,
        deadline_olovrant: '10:00',
        deadline_olovrant_is_day_before: false,
        edupage_auto_scrape_enabled: true,
        edupage_scrape_time_breakfast: null,
        edupage_scrape_time_breakfast_is_day_before: false,
        edupage_scrape_time_lunch: null,
        edupage_scrape_time_lunch_is_day_before: false,
        edupage_scrape_time_olovrant: null,
        edupage_scrape_time_olovrant_is_day_before: false,
        daily_report_enabled: true,
        report_email_recipients: [],
        client_contact_name: '',
        client_contact_role: '',
        client_contact_email: '',
        client_contact_phone: '',
    });
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<SettingsTab>('deadlines');
    const [newRecipient, setNewRecipient] = useState('');
    const [scrapeDate, setScrapeDate] = useState(() => {
        const now = new Date();
        const pad = (n: number) => String(n).padStart(2, '0');
        return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    });
    const [scraping, setScraping] = useState(false);
    const [connections, setConnections] = useState<EdupageConnection[]>([]);
    const [scrapeResults, setScrapeResults] = useState<ScrapeResult[]>([]);
    const [expandedResults, setExpandedResults] = useState<Set<number>>(() => new Set());

    const britishSchool = connections.find((c) => c.name === 'British School');

    const fetchConnections = React.useCallback(async () => {
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/edupage-connections/`);
            if (!res.ok) return;
            const data = await res.json();
            if (Array.isArray(data)) setConnections(data);
        } catch (e) {
            logger.error(e);
        }
    }, [apiFetch]);

    useEffect(() => {
        fetchConnections();
    }, [fetchConnections]);

    const fetchAutomation = React.useCallback(async () => {
        setAutomationLoading(true);
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/upcoming-events/`);
            if (res.ok) {
                const data = await res.json();
                setAutomation(data.results ?? []);
            }
        } catch (e) {
            logger.error(e);
        } finally {
            setAutomationLoading(false);
        }
    }, [apiFetch]);

    useEffect(() => {
        if (canSeeAutomation) void fetchAutomation();
    }, [canSeeAutomation, fetchAutomation]);

    const runScrapeNow = async (connectionId?: number) => {
        setScraping(true);
        setScrapeResults([]);
        setExpandedResults(new Set());
        try {
            const body: { date: string; connection_id?: number } = { date: scrapeDate };
            if (connectionId) body.connection_id = connectionId;
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/edupage-connections/scrape/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                error(data?.error || 'Načítanie z EduPage zlyhalo.');
                return;
            }
            const results: ScrapeResult[] = data?.results ?? [];
            setScrapeResults(results);
            const updated = results.filter((r) => r.status === 'updated').length;
            const orders = results.reduce((sum, r) => sum + (r.orders?.length ?? 0), 0);
            if (updated === 0) {
                error('Nenačítala sa žiadna prevádzka — skontroluj EduPage nastavenie.');
            } else {
                success(`Načítané z EduPage: ${updated} prevádzok, ${orders} objednávok (${scrapeDate}).`);
            }
        } catch (e) {
            logger.error(e);
            error('Načítanie z EduPage zlyhalo.');
        } finally {
            setScraping(false);
        }
    };

    const toggleResultExpanded = (connectionId: number) => {
        setExpandedResults((current) => {
            const next = new Set(current);
            if (next.has(connectionId)) next.delete(connectionId); else next.add(connectionId);
            return next;
        });
    };

    const fetchSettings = React.useCallback(async () => {
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`);
            if (res.ok) {
                const data = await res.json();
                setSettings(data);
            }
        } catch (e) {
            logger.error(e);
            error('Nepodarilo sa načítať nastavenia');
        } finally {
            setLoading(false);
        }
    }, [apiFetch, error]);

    useEffect(() => {
        fetchSettings();
    }, [fetchSettings]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await saveSettings();
    };

    const saveSettings = async () => {
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            if (res.ok) {
                success('Nastavenia boli úspešne uložené');
            } else {
                error('Chyba pri ukladaní nastavení');
            }
        } catch (e) {
            logger.error(e);
            error('Chyba pripojenia');
        }
    };

    const clearMaintenance = async () => {
        const cleared = {
            ...settings,
            maintenance_enabled: false,
            maintenance_starts_at: null,
            maintenance_ends_at: null,
        };
        setSettings(cleared);
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    maintenance_enabled: false,
                    maintenance_starts_at: null,
                    maintenance_ends_at: null,
                }),
            });
            if (res.ok) success('Údržba bola zmazaná');
            else {
                setSettings(settings);
                error('Údržbu sa nepodarilo zmazať');
            }
        } catch (e) {
            logger.error(e);
            setSettings(settings);
            error('Chyba pripojenia');
        }
    };

    if (loading) return <div className="zpa-empty">Načítavam…</div>;

    const maintenanceConfigured = Boolean(
        settings.maintenance_enabled || settings.maintenance_starts_at || settings.maintenance_ends_at,
    );
    const maintenanceActive = Boolean(
        settings.maintenance_enabled
        && settings.maintenance_starts_at
        && settings.maintenance_ends_at
        && new Date(settings.maintenance_starts_at).getTime() <= Date.now()
        && Date.now() < new Date(settings.maintenance_ends_at).getTime(),
    );
    const formatMaintenanceDate = (value: string | null) => value
        ? new Intl.DateTimeFormat('sk-SK', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
        : 'nezadané';

    const isValidEmail = (value: string): boolean => {
        const input = document.createElement('input');
        input.type = 'email';
        input.value = value;
        return input.checkValidity();
    };

    const addRecipient = async () => {
        const email = newRecipient.trim().toLowerCase();
        if (!email) return;
        if (!isValidEmail(email)) {
            error('Neplatná e-mailová adresa');
            return;
        }
        if (settings.report_email_recipients.includes(email)) {
            error('Táto adresa je už v zozname');
            return;
        }

        const newSettings: GlobalSettings = {
            ...settings,
            report_email_recipients: [...settings.report_email_recipients, email],
        };
        setSettings(newSettings);
        setNewRecipient('');

        // Auto-save only the recipients field after adding
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ report_email_recipients: newSettings.report_email_recipients }),
            });
            if (res.ok) {
                success('Príjemca bol úspešne pridaný');
            } else {
                error('Chyba pri pridávaní príjemcu');
                await fetchSettings();
            }
        } catch (e) {
            logger.error(e);
            error('Chyba pripojenia');
            await fetchSettings();
        }
    };

    const removeRecipient = async (email: string) => {
        const newSettings: GlobalSettings = {
            ...settings,
            report_email_recipients: settings.report_email_recipients.filter((r) => r !== email),
        };
        setSettings(newSettings);

        // Auto-save only the recipients field after removing
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ report_email_recipients: newSettings.report_email_recipients }),
            });
            if (res.ok) {
                success('Príjemca bol úspešne odstránený');
            } else {
                error('Chyba pri odstraňovaní príjemcu');
                await fetchSettings();
            }
        } catch (e) {
            logger.error(e);
            error('Chyba pripojenia');
            await fetchSettings();
        }
    };

    const toggleDailyReport = async (enabled: boolean) => {
        setSettings({ ...settings, daily_report_enabled: enabled });

        // Auto-save only the flag; the recipient list stays untouched.
        try {
            const res = await apiFetch(`${import.meta.env.VITE_API_URL || '/api'}/admin/global-settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ daily_report_enabled: enabled }),
            });
            if (res.ok) {
                success(enabled ? 'Denné reporty sú zapnuté' : 'Denné reporty sú vypnuté');
            } else {
                error('Chyba pri ukladaní nastavenia');
                await fetchSettings();
            }
        } catch (e) {
            logger.error(e);
            error('Chyba pripojenia');
            await fetchSettings();
        }
    };

    const deadlineField = (
        label: string,
        timeKey: 'deadline_breakfast' | 'deadline_lunch' | 'deadline_olovrant',
        dayBeforeKey: 'deadline_breakfast_is_day_before' | 'deadline_lunch_is_day_before' | 'deadline_olovrant_is_day_before',
    ) => (
        <div>
            <Field label={label}>
                <Input
                    type="time"
                    value={settings[timeKey]?.slice(0, 5)}
                    onChange={(e) => setSettings({ ...settings, [timeKey]: e.target.value })}
                />
            </Field>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, cursor: 'pointer', userSelect: 'none' }}>
                <input
                    type="checkbox"
                    checked={settings[dayBeforeKey]}
                    onChange={(e) => setSettings({ ...settings, [dayBeforeKey]: e.target.checked })}
                    style={{ width: 16, height: 16, accentColor: 'var(--green-600)' }}
                />
                <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Uzávierka deň vopred</span>
            </label>
        </div>
    );

    const scrapeOverrideField = (
        label: string,
        timeKey: 'edupage_scrape_time_breakfast' | 'edupage_scrape_time_lunch' | 'edupage_scrape_time_olovrant',
        dayBeforeKey:
            | 'edupage_scrape_time_breakfast_is_day_before'
            | 'edupage_scrape_time_lunch_is_day_before'
            | 'edupage_scrape_time_olovrant_is_day_before',
    ) => {
        const overridden = settings[timeKey] !== null;
        return (
            <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}>
                    <input
                        type="checkbox"
                        checked={overridden}
                        onChange={(e) => setSettings({
                            ...settings,
                            [timeKey]: e.target.checked ? '01:35' : null,
                        })}
                        style={{ width: 16, height: 16, accentColor: 'var(--green-600)' }}
                    />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
                </label>
                {overridden && (
                    <div style={{ marginTop: 10, marginLeft: 24, display: 'flex', flexDirection: 'column', gap: 10 }}>
                        <Field label="Čas scrapu">
                            <Input
                                type="time"
                                value={settings[timeKey]?.slice(0, 5) ?? ''}
                                onChange={(e) => setSettings({ ...settings, [timeKey]: e.target.value })}
                                style={{ width: 'auto' }}
                            />
                        </Field>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}>
                            <input
                                type="checkbox"
                                checked={settings[dayBeforeKey]}
                                onChange={(e) => setSettings({ ...settings, [dayBeforeKey]: e.target.checked })}
                                style={{ width: 16, height: 16, accentColor: 'var(--green-600)' }}
                            />
                            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Cieli na nasledujúci pracovný deň</span>
                        </label>
                    </div>
                )}
            </div>
        );
    };

    return (
        <>
            <PageHead eyebrow="Nastavenia" title="Systémové nastavenia" />

            <div className="zpa-tabs" style={{ maxWidth: 'fit-content' }}>
                {TABS.map((t) => (
                    <button
                        key={t.key}
                        type="button"
                        onClick={() => setActiveTab(t.key)}
                        className={`zpa-tab${activeTab === t.key ? ' active' : ''}`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            <div className="zpa-stack" style={{ maxWidth: 860, marginTop: 20 }}>
                {/* Časy: uzávierky, EduPage scrape override, prehľad ostatnej automatiky */}
                {activeTab === 'deadlines' && (
                <>
                <Card pad>
                    <CardHead title="Časy uzávierok objednávok" />
                    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 24, marginTop: 8 }}>
                        <div className="zpa-grid-3">
                            {deadlineField('Raňajky', 'deadline_breakfast', 'deadline_breakfast_is_day_before')}
                            {deadlineField('Obed', 'deadline_lunch', 'deadline_lunch_is_day_before')}
                            {deadlineField('Olovrant', 'deadline_olovrant', 'deadline_olovrant_is_day_before')}
                        </div>
                        <div style={{ paddingTop: 24, borderTop: '1px solid var(--line-soft)', display: 'flex', justifyContent: 'flex-end' }}>
                            <Button type="submit">Uložiť zmeny</Button>
                        </div>
                    </form>
                </Card>

                <Card pad style={{ marginTop: 20 }}>
                    <CardHead
                        title="Čas EduPage scrapu"
                        desc="Bez zaškrtnutia sa scrapuje presne pri uzávierke daného jedla. Zaškrtnutím nastavíš iný čas — napr. uzávierka na raňajky ostane 21:00 večer predtým, ale scrape pobeží až 1:35 v deň raňajok."
                    />
                    <div className="zpa-grid-3" style={{ marginTop: 12 }}>
                        {scrapeOverrideField('Raňajky', 'edupage_scrape_time_breakfast', 'edupage_scrape_time_breakfast_is_day_before')}
                        {scrapeOverrideField('Obed', 'edupage_scrape_time_lunch', 'edupage_scrape_time_lunch_is_day_before')}
                        {scrapeOverrideField('Olovrant', 'edupage_scrape_time_olovrant', 'edupage_scrape_time_olovrant_is_day_before')}
                    </div>
                    <div style={{ paddingTop: 24, borderTop: '1px solid var(--line-soft)', marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
                        <Button type="button" onClick={saveSettings}>Uložiť zmeny</Button>
                    </div>
                </Card>

                {canSeeAutomation && (
                    <Card pad style={{ marginTop: 20 }}>
                        <CardHead
                            title="Prehľad všetkých automatických behov"
                            desc="Needitovateľné tu — niektoré časy (push pripomienky, auto-objednávky) sa odvíjajú od uzávierok vyššie, iné (týždenná pripomienka, British School, čistenie záznamov) sú pevne dané. Presný najbližší beh nájdeš v Logy → Nadchádzajúce."
                        />
                        {automationLoading ? (
                            <p style={{ fontSize: 13, color: 'var(--ink-mute)', marginTop: 12 }}>Načítavam…</p>
                        ) : automation.length === 0 ? (
                            <p style={{ fontSize: 13, color: 'var(--ink-mute)', marginTop: 12 }}>Žiadne naplánované úlohy.</p>
                        ) : (
                            <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
                                {automation.map((entry) => (
                                    <li key={entry.name} style={{ background: 'var(--bg-cream-soft)', borderRadius: 'var(--radius-md)', padding: '10px 14px' }}>
                                        <div style={{ fontSize: 13, fontWeight: 600 }}>
                                            {AUTOMATION_TASK_LABELS_SK[entry.task] ?? entry.name}
                                        </div>
                                        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 4 }}>
                                            {entry.description || entry.task}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </Card>
                )}
                </>
                )}

                {/* EduPage automation */}
                {activeTab === 'edupage' && (
                <Card pad>
                    <CardHead title="EduPage automatika" />
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginTop: 8 }}>
                        <div>
                            <p style={{ fontSize: 14, color: 'var(--ink-3)', margin: 0 }}>
                                Automatické čítanie objednávok z EduPage pred uzávierkami.
                            </p>
                            <p style={{ fontSize: 12.5, color: 'var(--ink-mute)', marginTop: 8 }}>
                                Automaticky beží len scrape pred uzávierkou (čas nastavíš
                                v tabe Časy). Ranné načítanie aktuálnych počtov spusti ručne
                                nižšie.
                            </p>
                        </div>
                        <Toggle
                            on={settings.edupage_auto_scrape_enabled}
                            onChange={(v) => setSettings({ ...settings, edupage_auto_scrape_enabled: v })}
                            ariaLabel="Automatické čítanie EduPage"
                        />
                    </div>

                    <div style={{ borderTop: '1px solid var(--line)', marginTop: 20, paddingTop: 20 }}>
                        <p style={{ fontSize: 14, color: 'var(--ink-3)', margin: 0 }}>
                            Načítať teraz z EduPage
                        </p>
                        <p style={{ fontSize: 12.5, color: 'var(--ink-mute)', marginTop: 8 }}>
                            Prepíše objednávky EduPage prevádzok pre zvolený deň aktuálnymi
                            počtami. Použi ráno, keď rodičia po večernom scrape odhlásili deti.
                        </p>
                        {/* `flexWrap` kvôli úzkym displejom: tlačidlo má nowrap
                            a vedľa dátumu sa na 320px nezmestí. */}
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end', marginTop: 12 }}>
                            <Field label="Deň">
                                <Input
                                    type="date"
                                    value={scrapeDate}
                                    onChange={(e) => setScrapeDate(e.target.value)}
                                    style={{ width: 'auto' }}
                                />
                            </Field>
                            <Button type="button" onClick={() => runScrapeNow()} disabled={scraping}>
                                {scraping ? 'Načítavam…' : 'Načítať z EduPage'}
                            </Button>
                            {britishSchool && (
                                <Button
                                    type="button"
                                    variant="secondary"
                                    onClick={() => runScrapeNow(britishSchool.id)}
                                    disabled={scraping}
                                >
                                    {scraping ? 'Načítavam…' : 'Scrapovať len British School'}
                                </Button>
                            )}
                        </div>

                        {scrapeResults.length > 0 && (
                            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {scrapeResults.map((r) => {
                                    const isExpanded = expandedResults.has(r.connection_id);
                                    const hasDetail = Boolean(
                                        r.reason || r.error
                                        || r.warnings?.length || r.unmapped_letters?.length
                                        || r.config_notes?.length || r.attention?.length,
                                    );
                                    const orderCount = r.orders?.length ?? 0;
                                    return (
                                        <div key={r.connection_id} style={{ background: 'var(--bg-cream-soft)', borderRadius: 'var(--radius-md)', padding: '10px 14px' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                                                <span style={{ fontSize: 13.5, fontWeight: 600 }}>{r.name}</span>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                                                        {r.status === 'updated' ? `${orderCount} prevádzok` : r.status}
                                                    </span>
                                                    {hasDetail && (
                                                        <Button variant="ghost" sm onClick={() => toggleResultExpanded(r.connection_id)}>
                                                            Detail
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                            {isExpanded && hasDetail && (
                                                <pre className="tb" style={{ marginTop: 8 }}>
                                                    {[
                                                        r.reason && `Dôvod: ${r.reason}`,
                                                        r.error && `Chyba: ${r.error}`,
                                                        r.warnings?.length ? `Warnings: ${r.warnings.join(', ')}` : null,
                                                        r.unmapped_letters?.length ? `Neznáme diéty: ${r.unmapped_letters.join(', ')}` : null,
                                                        r.config_notes?.length ? `Config poznámky: ${r.config_notes.join(', ')}` : null,
                                                        r.attention?.length ? `Pozor: ${r.attention.join(', ')}` : null,
                                                    ].filter(Boolean).join('\n')}
                                                </pre>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    <div style={{ paddingTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
                        <Button type="button" onClick={saveSettings}>Uložiť EduPage</Button>
                    </div>
                </Card>
                )}

                {/* Contact */}
                {activeTab === 'contact' && (
                <Card pad>
                    <CardHead title="Kontakt pre prevádzky" desc="Tieto údaje sa zobrazujú prevádzkam pri porciách a diétach." />
                    <div className="zpa-grid-2" style={{ marginTop: 8 }}>
                        <Input value={settings.client_contact_name} onChange={(e) => setSettings({ ...settings, client_contact_name: e.target.value })} placeholder="Meno kontaktnej osoby" />
                        <Input value={settings.client_contact_role} onChange={(e) => setSettings({ ...settings, client_contact_role: e.target.value })} placeholder="Rola / poznámka" />
                        <Input type="email" value={settings.client_contact_email} onChange={(e) => setSettings({ ...settings, client_contact_email: e.target.value })} placeholder="kontakt@priklad.sk" />
                        <Input type="tel" value={settings.client_contact_phone} onChange={(e) => setSettings({ ...settings, client_contact_phone: e.target.value })} placeholder="+421..." />
                    </div>
                    <div style={{ paddingTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
                        <Button type="button" onClick={saveSettings}>Uložiť kontakt</Button>
                    </div>
                </Card>
                )}

                {/* Report email recipients */}
                {activeTab === 'report' && (
                <Card pad>
                    <CardHead title="Príjemcovia denného reportu" desc="Na tieto e-mailové adresy bude automaticky zasielaný denný prehľad objednávok (XLSX)." />
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginTop: 8 }}>
                        <div>
                            <p style={{ fontSize: 14, color: 'var(--ink-3)', margin: 0 }}>
                                Automatické odosielanie denného reportu
                            </p>
                            <p style={{ fontSize: 12.5, color: 'var(--ink-mute)', marginTop: 8 }}>
                                Keď je vypnuté, report sa neodosiela, ale zoznam príjemcov
                                nižšie zostáva zachovaný.
                            </p>
                        </div>
                        <Toggle
                            on={settings.daily_report_enabled}
                            onChange={toggleDailyReport}
                            ariaLabel="Automatické odosielanie denného reportu"
                        />
                    </div>

                    <div style={{ display: 'flex', gap: 12, margin: '20px 0 16px', borderTop: '1px solid var(--line)', paddingTop: 20 }}>
                        <Input
                            type="email"
                            value={newRecipient}
                            onChange={(e) => setNewRecipient(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    addRecipient();
                                }
                            }}
                            placeholder="email@priklad.sk"
                        />
                        <Button type="button" onClick={addRecipient}><Plus /> Pridať</Button>
                    </div>

                    {settings.report_email_recipients.length === 0 ? (
                        <p style={{ fontSize: 14, color: 'var(--ink-mute)', fontStyle: 'italic', margin: 0 }}>
                            Žiadni príjemcovia nie sú nakonfigurovaní.
                        </p>
                    ) : (
                        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {settings.report_email_recipients.map((email) => (
                                <li key={email} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-cream-soft)', borderRadius: 'var(--radius-md)', padding: '12px 16px' }}>
                                    <span style={{ fontSize: 14, color: 'var(--green-900)' }}>{email}</span>
                                    <button type="button" onClick={() => removeRecipient(email)} style={{ border: 0, background: 'none', cursor: 'pointer', color: 'var(--coral-600)', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-display)' }}>
                                        Odstrániť
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
                )}

                {activeTab === 'maintenance' && (
                <Card pad>
                    <CardHead title="Plánovaná údržba" desc="Počas aktívneho intervalu klienti uvidia oznam s odpočtom a nemôžu sa prihlásiť ani odosielať objednávky. Admin a superadmin majú prístup ďalej." />
                    <div style={{ marginTop: 16, padding: '14px 16px', borderRadius: 'var(--radius-md)', background: 'var(--bg-cream-soft)', border: '1px solid var(--line-soft)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                            <strong style={{ fontSize: 14, color: 'var(--green-900)' }}>Aktuálna údržba</strong>
                            <span className={`zpa-badge zpa-badge--${maintenanceActive ? 'coral' : maintenanceConfigured ? 'honey' : 'gray'}`}>
                                {maintenanceActive ? 'Aktívna' : maintenanceConfigured ? 'Naplánovaná' : 'Nie je nastavená'}
                            </span>
                        </div>
                        {maintenanceConfigured && <p style={{ margin: '9px 0 0', fontSize: 13, color: 'var(--ink-3)' }}>
                            {formatMaintenanceDate(settings.maintenance_starts_at)} — {formatMaintenanceDate(settings.maintenance_ends_at)}
                        </p>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginTop: 12 }}>
                        <div>
                            <p style={{ fontSize: 14, color: 'var(--ink-3)', margin: 0 }}>Zapnúť režim údržby</p>
                            <p style={{ fontSize: 12.5, color: 'var(--ink-mute)', marginTop: 6 }}>Oznam sa zobrazí automaticky medzi časmi nižšie.</p>
                        </div>
                        <Toggle on={settings.maintenance_enabled ?? false} onChange={(value) => setSettings({ ...settings, maintenance_enabled: value })} ariaLabel="Zapnúť režim údržby" />
                    </div>
                    <div className="zpa-grid-2" style={{ marginTop: 20 }}>
                        <Field label="Začiatok údržby"><Input type="datetime-local" value={settings.maintenance_starts_at ? settings.maintenance_starts_at.slice(0, 16) : ''} onChange={(e) => setSettings({ ...settings, maintenance_starts_at: e.target.value || null })} /></Field>
                        <Field label="Koniec údržby — objednávky budú opäť dostupné"><Input type="datetime-local" value={settings.maintenance_ends_at ? settings.maintenance_ends_at.slice(0, 16) : ''} onChange={(e) => setSettings({ ...settings, maintenance_ends_at: e.target.value || null })} /></Field>
                    </div>
                    <div style={{ paddingTop: 24, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        {maintenanceConfigured ? <Button type="button" variant="danger" onClick={clearMaintenance}>Zmazať údržbu</Button> : <span />}
                        <Button type="button" onClick={saveSettings}>Uložiť údržbu</Button>
                    </div>
                </Card>
                )}

                {/* Billing coefficients */}
            </div>
        </>
    );
};

export default SystemSettings;
